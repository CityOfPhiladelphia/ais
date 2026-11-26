"""Build `service_area_summary` using parallelized PostGIS spatial joins and GiST KNN.

Performance optimizations:
- Uses `UNLOGGED` staging tables (dropped in `finally`) instead of `TEMP TABLE`s so
  PostgreSQL 17 can parallelize spatial joins, hash aggregates, and GiST KNN lookups
  across all CPU cores (`TEMP TABLE`s disable parallel query workers in PostgreSQL).
- Materializes distinct `(geocode_x, geocode_y)` points with a compact integer `pt_id`
  key so co-located unit/condo addresses only run spatial joins and KNN lookups once.
- Subdivides complex service area polygons via `ST_Subdivide(..., 64)` into a GiST-indexed
  UNLOGGED table while deduplicating tiles by source polygon `id`.
- Computes all KNN (`nearest` point / `nearest_poly`) layers in one parallel pass over
  distinct points using per-layer GiST-indexed UNLOGGED tables (`<->`).
- Pivots all `line_single`, `line_dual`, and `seg_id` point layers into one tiny
  segment-level lookup table (~40k rows).
- Populates `service_area_summary` in a SINGLE `INSERT ... SELECT` (applying layer
  override precedence and `yes_or_no` normalization inline) — eliminating 17 full-table
  `UPDATE` rewrites, dead tuples, and MVCC bloat.
- Preserves existing `address_summary` indexes during the `zip_code` backfill (none of
  them index `zip_code`, enabling HOT updates without rebuilding the GIN trigram index).
"""

from datetime import datetime
from ais import app
from ais.engine.db import connect


def _build_layer_select_expr(layer_def: dict) -> str:
    """Build the SQL expression for a single service_area_summary column.

    Preserves exact override precedence from lowest to highest:
    polygon -> line_single -> line_dual -> point(nearest) -> point(seg_id) -> nearest_poly,
    followed by optional `yes_or_no` normalization.
    """
    lid = layer_def["layer_id"]
    sources = layer_def["sources"]

    # Build candidates from HIGHEST precedence to LOWEST for COALESCE(..., '')
    candidates: list[str] = []

    poly_src = sources.get("polygon")
    if poly_src and poly_src.get("method") == "nearest_poly":
        candidates.append(f'knn."{lid}"')

    pt_src = sources.get("point")
    if pt_src:
        pt_method = pt_src.get("method")
        if pt_method == "seg_id":
            candidates.append(f'NULLIF(seg."{lid}__pt", \'\')')
        elif pt_method == "nearest":
            candidates.append(f'knn."{lid}"')

    if "line_dual" in sources:
        side_expr = (
            f'CASE WHEN ads.seg_side = \'L\' THEN seg."{lid}__L" ELSE seg."{lid}__R" END'
        )
        candidates.append(f"NULLIF({side_expr}, '')")

    if "line_single" in sources:
        candidates.append(f'NULLIF(seg."{lid}", \'\')')

    if poly_src and poly_src.get("method") != "nearest_poly":
        candidates.append(f'pt."{lid}"')

    candidates.append("''")
    expr = f"COALESCE({', '.join(candidates)})"

    if layer_def.get("value_method") == "yes_or_no":
        return f"CASE WHEN {expr} != '' THEN 'Yes' ELSE 'No' END"
    return expr


def main():
    print("Starting make_service_area_summary...")
    start = datetime.now()

    config = app.config
    engine_srid = int(config["ENGINE_SRID"])
    db = connect(config["DATABASES"]["engine"])
    sa_layer_defs = config["SERVICE_AREAS"]["layers"]
    sa_layer_ids = [x["layer_id"] for x in sa_layer_defs]

    # Classify layers by source type
    poly_layer_ids = [
        d["layer_id"]
        for d in sa_layer_defs
        if "polygon" in d["sources"] and d["sources"]["polygon"].get("method") != "nearest_poly"
    ]
    line_single_ids = [
        d["layer_id"] for d in sa_layer_defs if "line_single" in d["sources"]
    ]
    line_dual_ids = [
        d["layer_id"] for d in sa_layer_defs if "line_dual" in d["sources"]
    ]
    seg_point_ids = [
        d["layer_id"]
        for d in sa_layer_defs
        if "point" in d["sources"] and d["sources"]["point"].get("method") == "seg_id"
    ]
    knn_layers: list[tuple[str, str]] = []  # (layer_id, source_table)
    for d in sa_layer_defs:
        lid = d["layer_id"]
        if "point" in d["sources"] and d["sources"]["point"].get("method") == "nearest":
            knn_layers.append((lid, "service_area_point"))
        elif (
            "polygon" in d["sources"]
            and d["sources"]["polygon"].get("method") == "nearest_poly"
        ):
            knn_layers.append((lid, "service_area_polygon"))

    staging_tables = [
        "_sa_tmp_pts",
        "_sa_tmp_poly_sub",
        "_sa_tmp_pt_vals",
        "_sa_tmp_knn_vals",
        "_sa_tmp_seg_vals",
    ] + [f"_sa_tmp_knn_src_{i}" for i in range(len(knn_layers))]

    def _drop_staging_tables():
        for tbl in staging_tables:
            db.execute(f"DROP TABLE IF EXISTS {tbl};")
        db.save()

    try:
        # Allow PostgreSQL parallel workers & generous hash memory on this session
        db.execute("SET work_mem = '256MB';")
        _drop_staging_tables()

        sa_summary_fields = [{"name": "street_address", "type": "text"}]
        sa_summary_fields += [{"name": layer_id, "type": "text"} for layer_id in sa_layer_ids]

        print("Recreating service_area_summary table...")
        db.drop_table("service_area_summary")
        db.create_table("service_area_summary", sa_summary_fields)

        print("Ensuring spatial index and stats on service_area_polygon...")
        db.execute("""
            CREATE INDEX IF NOT EXISTS service_area_polygon_geom_gix
                ON service_area_polygon USING GIST (geom);
            ANALYZE service_area_polygon;
            ANALYZE address_summary;
        """)
        db.save()

        # ---------------------------------------------------------------------
        # 1. Materialize distinct geocoded points & subdivided polygons (UNLOGGED)
        # ---------------------------------------------------------------------
        print("Building UNLOGGED indexed tables for distinct points and subdivided polygons...")
        poly_filter_sql = (
            "AND layer_id IN (" + ", ".join(f"'{lid}'" for lid in poly_layer_ids) + ")"
            if poly_layer_ids
            else "AND FALSE"
        )
        db.execute(f"""
            CREATE UNLOGGED TABLE _sa_tmp_pts AS
            SELECT
                row_number() OVER () AS pt_id,
                geocode_x,
                geocode_y,
                ST_SetSRID(ST_MakePoint(geocode_x, geocode_y), {engine_srid}) AS geom
            FROM (
                SELECT DISTINCT geocode_x, geocode_y
                FROM address_summary
                WHERE geocode_x IS NOT NULL AND geocode_y IS NOT NULL
            ) d;

            CREATE INDEX _sa_tmp_pts_gix ON _sa_tmp_pts USING GIST (geom);
            CREATE INDEX _sa_tmp_pts_xy_idx ON _sa_tmp_pts (geocode_x, geocode_y);
            ANALYZE _sa_tmp_pts;

            CREATE UNLOGGED TABLE _sa_tmp_poly_sub AS
            SELECT
                id AS poly_id,
                layer_id,
                value,
                sub_geom AS geom
            FROM (
                SELECT
                    id,
                    layer_id,
                    value,
                    ST_Subdivide(
                        CASE
                            WHEN ST_IsValid(geom) THEN geom
                            ELSE ST_CollectionExtract(ST_MakeValid(geom), 3)
                        END,
                        64
                    ) AS sub_geom
                FROM service_area_polygon
                WHERE geom IS NOT NULL {poly_filter_sql}
            ) s
            WHERE sub_geom IS NOT NULL AND NOT ST_IsEmpty(sub_geom);

            CREATE INDEX _sa_tmp_poly_sub_gix ON _sa_tmp_poly_sub USING GIST (geom);
            ANALYZE _sa_tmp_poly_sub;
        """)
        db.save()

        # ---------------------------------------------------------------------
        # 2. Parallel PostGIS spatial join for all polygon service areas
        # ---------------------------------------------------------------------
        print(f"Running parallel spatial join across {len(poly_layer_ids)} polygon layers...")
        poly_pivot_sql = ",\n                ".join(
            f"COALESCE(MAX(CASE WHEN layer_id = '{lid}' THEN agg_val END), '') AS \"{lid}\""
            for lid in poly_layer_ids
        )
        if poly_layer_ids:
            db.execute(f"""
                CREATE UNLOGGED TABLE _sa_tmp_pt_vals AS
                WITH distinct_poly_hits AS (
                    SELECT DISTINCT
                        dp.pt_id,
                        poly.poly_id,
                        poly.layer_id,
                        poly.value
                    FROM _sa_tmp_pts dp
                    JOIN _sa_tmp_poly_sub poly
                      ON ST_Intersects(poly.geom, dp.geom)
                ),
                pt_layer_vals AS (
                    SELECT
                        pt_id,
                        layer_id,
                        string_agg(value, '|' ORDER BY value) AS agg_val
                    FROM distinct_poly_hits
                    GROUP BY pt_id, layer_id
                ),
                pivoted AS (
                    SELECT
                        pt_id,
                        {poly_pivot_sql}
                    FROM pt_layer_vals
                    GROUP BY pt_id
                )
                SELECT
                    dp.geocode_x,
                    dp.geocode_y,
                    {", ".join(f'p."{lid}"' for lid in poly_layer_ids)}
                FROM _sa_tmp_pts dp
                JOIN pivoted p ON p.pt_id = dp.pt_id;

                CREATE INDEX _sa_tmp_pt_vals_xy_idx ON _sa_tmp_pt_vals (geocode_x, geocode_y);
                ANALYZE _sa_tmp_pt_vals;
                DROP TABLE IF EXISTS _sa_tmp_poly_sub;
            """)
            db.save()

        # ---------------------------------------------------------------------
        # 3. Parallel GiST KNN for nearest point / nearest_poly layers
        # ---------------------------------------------------------------------
        if knn_layers:
            print(f"Running parallel GiST KNN across {len(knn_layers)} nearest layer(s)...")
            knn_selects = []
            knn_joins = []
            for idx, (lid, src_table) in enumerate(knn_layers):
                src_tmp = f"_sa_tmp_knn_src_{idx}"
                db.execute(f"""
                    CREATE UNLOGGED TABLE {src_tmp} AS
                    SELECT value, geom
                    FROM {src_table}
                    WHERE layer_id = '{lid}' AND geom IS NOT NULL;

                    CREATE INDEX {src_tmp}_gix ON {src_tmp} USING GIST (geom);
                    ANALYZE {src_tmp};
                """)
                knn_selects.append(f'k{idx}.value AS "{lid}"')
                knn_joins.append(
                    f"""LEFT JOIN LATERAL (
                        SELECT l.value
                        FROM {src_tmp} l
                        ORDER BY dp.geom <-> l.geom
                        LIMIT 1
                    ) k{idx} ON true"""
                )
            db.save()

            db.execute(f"""
                CREATE UNLOGGED TABLE _sa_tmp_knn_vals AS
                SELECT
                    dp.geocode_x,
                    dp.geocode_y,
                    {", ".join(knn_selects)}
                FROM _sa_tmp_pts dp
                {" ".join(knn_joins)};

                CREATE INDEX _sa_tmp_knn_vals_xy_idx ON _sa_tmp_knn_vals (geocode_x, geocode_y);
                ANALYZE _sa_tmp_knn_vals;
            """)
            for idx in range(len(knn_layers)):
                db.execute(f"DROP TABLE IF EXISTS _sa_tmp_knn_src_{idx};")
            db.save()

        db.execute("DROP TABLE IF EXISTS _sa_tmp_pts;")
        db.save()

        # ---------------------------------------------------------------------
        # 4. Pivot all segment-based layers (line_single, line_dual, seg_id point)
        # ---------------------------------------------------------------------
        has_seg_layers = bool(line_single_ids or line_dual_ids or seg_point_ids)
        if has_seg_layers:
            print("Building segment-based service area lookup table...")
            union_parts = []
            seg_pivot_cols = []

            if line_single_ids:
                in_sql = ", ".join(f"'{lid}'" for lid in line_single_ids)
                union_parts.append(f"""
                    SELECT seg_id, layer_id AS col_key, value AS val
                    FROM service_area_line_single
                    WHERE layer_id IN ({in_sql}) AND value IS NOT NULL AND value <> ''
                """)
                for lid in line_single_ids:
                    seg_pivot_cols.append(
                        f"MAX(val) FILTER (WHERE col_key = '{lid}') AS \"{lid}\""
                    )

            if line_dual_ids:
                in_sql = ", ".join(f"'{lid}'" for lid in line_dual_ids)
                union_parts.append(f"""
                    SELECT seg_id, layer_id || '__L' AS col_key, left_value AS val
                    FROM service_area_line_dual
                    WHERE layer_id IN ({in_sql}) AND left_value IS NOT NULL AND left_value <> ''
                """)
                union_parts.append(f"""
                    SELECT seg_id, layer_id || '__R' AS col_key, right_value AS val
                    FROM service_area_line_dual
                    WHERE layer_id IN ({in_sql}) AND right_value IS NOT NULL AND right_value <> ''
                """)
                for lid in line_dual_ids:
                    seg_pivot_cols.append(
                        f"MAX(val) FILTER (WHERE col_key = '{lid}__L') AS \"{lid}__L\""
                    )
                    seg_pivot_cols.append(
                        f"MAX(val) FILTER (WHERE col_key = '{lid}__R') AS \"{lid}__R\""
                    )

            if seg_point_ids:
                in_sql = ", ".join(f"'{lid}'" for lid in seg_point_ids)
                union_parts.append(f"""
                    SELECT seg_id, layer_id || '__pt' AS col_key, value AS val
                    FROM service_area_point
                    WHERE layer_id IN ({in_sql}) AND value IS NOT NULL AND value <> ''
                """)
                for lid in seg_point_ids:
                    seg_pivot_cols.append(
                        f"MAX(val) FILTER (WHERE col_key = '{lid}__pt') AS \"{lid}__pt\""
                    )

            db.execute(f"""
                CREATE UNLOGGED TABLE _sa_tmp_seg_vals AS
                WITH raw_seg AS (
                    {" UNION ALL ".join(union_parts)}
                )
                SELECT
                    seg_id,
                    {", ".join(seg_pivot_cols)}
                FROM raw_seg
                GROUP BY seg_id;

                CREATE INDEX _sa_tmp_seg_vals_seg_id_idx ON _sa_tmp_seg_vals (seg_id);
                ANALYZE _sa_tmp_seg_vals;
            """)
            db.save()

        # ---------------------------------------------------------------------
        # 5. Single-pass INSERT into service_area_summary (zero full-table UPDATEs)
        # ---------------------------------------------------------------------
        print("Populating service_area_summary in a single pass...")
        col_names_sql = ", ".join(f'"{lid}"' for lid in sa_layer_ids)
        select_exprs_sql = ",\n            ".join(
            f'{_build_layer_select_expr(d)} AS "{d["layer_id"]}"'
            for d in sa_layer_defs
        )

        joins = []
        if poly_layer_ids:
            joins.append(
                "LEFT JOIN _sa_tmp_pt_vals pt "
                "ON ads.geocode_x = pt.geocode_x AND ads.geocode_y = pt.geocode_y"
            )
        if knn_layers:
            joins.append(
                "LEFT JOIN _sa_tmp_knn_vals knn "
                "ON ads.geocode_x = knn.geocode_x AND ads.geocode_y = knn.geocode_y"
            )
        if has_seg_layers:
            joins.append("LEFT JOIN _sa_tmp_seg_vals seg ON ads.seg_id = seg.seg_id")

        db.execute(f"""
            INSERT INTO service_area_summary (street_address, {col_names_sql})
            SELECT
                ads.street_address,
                {select_exprs_sql}
            FROM address_summary ads
            {" ".join(joins)};
        """)
        db.save()

        # Drop staging tables before indexing to reclaim memory/disk
        _drop_staging_tables()

        print("Indexing service_area_summary...")
        sa_summary_table = db["service_area_summary"]
        sa_summary_table.create_index("street_address")
        db.execute("ANALYZE service_area_summary;")
        db.save()

        # ---------------------------------------------------------------------
        # 6. Backfill missing zip_codes & ensure all required address_summary indexes
        # ---------------------------------------------------------------------
        print("Backfilling null address_summary zip_codes from service_area_summary...")
        db.execute("""
            UPDATE address_summary asum
            SET zip_code = sas.zip_code
            FROM service_area_summary sas
            WHERE sas.street_address = asum.street_address
              AND (asum.zip_code IS NULL OR asum.zip_code = '')
              AND sas.zip_code IS NOT NULL
              AND sas.zip_code != '';

            CREATE INDEX IF NOT EXISTS ix_address_summary_seg_id
                ON public.address_summary USING btree (seg_id);
            CREATE INDEX IF NOT EXISTS address_summary_opa_owners_trigram_idx
                ON public.address_summary USING gin (opa_owners gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS address_summary_sort_idx
                ON public.address_summary USING btree
                (street_name, street_suffix, street_predir, street_postdir, address_low, address_high, unit_num);
            CREATE INDEX IF NOT EXISTS address_summary_street_address_idx
                ON public.address_summary USING btree (street_address);
            CREATE INDEX IF NOT EXISTS ix_address_summary_dor_parcel_id
                ON public.address_summary USING btree (dor_parcel_id);
            CREATE INDEX IF NOT EXISTS ix_address_summary_opa_account_num
                ON public.address_summary USING btree (opa_account_num);
            CREATE INDEX IF NOT EXISTS ix_address_summary_pwd_parcel_id
                ON public.address_summary USING btree (pwd_parcel_id);
        """)
        db.save()
    except Exception:
        db.conn.rollback()
        raise
    finally:
        _drop_staging_tables()
        db.close()

    print(f"Finished make_service_area_summary in {datetime.now() - start}")
