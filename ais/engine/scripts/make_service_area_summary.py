"""Build `service_area_summary` using subdivided PostGIS spatial joins and GiST KNN.

Performance optimizations:
- Materializes distinct `(geocode_x, geocode_y)` points into an indexed TEMP table
  so co-located unit/condo addresses only perform spatial joins and KNN lookups once.
- Subdivides large complex service area polygons via `ST_Subdivide(..., 64)` into a
  GiST-indexed TEMP table, giving 10x-50x faster `ST_Intersects` against large citywide
  polygons while deduplicating tiles by source polygon `id`.
- Builds per-layer GiST-indexed TEMP tables for `nearest` point and `nearest_poly`
  layers so PostgreSQL uses a true GiST KNN index scan (`<->`) instead of full scans.
- Consolidates all `yes_or_no` updates into a single table scan.
- Preserves existing `address_summary` indexes during the `zip_code` backfill (none of
  them index `zip_code`, enabling HOT updates without rebuilding the GIN trigram index).
"""

from datetime import datetime
from ais import app
from ais.engine.db import connect


def main():
    print("Starting make_service_area_summary...")
    start = datetime.now()

    config = app.config
    engine_srid = int(config["ENGINE_SRID"])
    db = connect(config["DATABASES"]["engine"])
    sa_layer_defs = config["SERVICE_AREAS"]["layers"]
    sa_layer_ids = [x["layer_id"] for x in sa_layer_defs]

    sa_summary_fields = [{"name": "street_address", "type": "text"}]
    sa_summary_fields += [{"name": layer_id, "type": "text"} for layer_id in sa_layer_ids]

    print("Recreating service_area_summary table...")
    db.drop_table("service_area_summary")
    db.create_table("service_area_summary", sa_summary_fields)

    # Ensure GiST spatial index & fresh planner stats on service_area_polygon
    print("Ensuring spatial index and stats on service_area_polygon...")
    db.execute("""
        CREATE INDEX IF NOT EXISTS service_area_polygon_geom_gix
            ON service_area_polygon USING GIST (geom);
        ANALYZE service_area_polygon;
        ANALYZE address_summary;
    """)
    db.save()

    # -------------------------------------------------------------------------
    # 1. Materialize distinct geocoded points & subdivided polygons (GiST indexed)
    # -------------------------------------------------------------------------
    print("Building indexed temp tables for distinct points and subdivided polygons...")
    db.execute(f"""
        CREATE TEMP TABLE tmp_distinct_pts AS
        SELECT DISTINCT
            geocode_x,
            geocode_y,
            ST_SetSRID(ST_MakePoint(geocode_x, geocode_y), {engine_srid}) AS geom
        FROM address_summary
        WHERE geocode_x IS NOT NULL AND geocode_y IS NOT NULL;

        CREATE INDEX tmp_distinct_pts_gix ON tmp_distinct_pts USING GIST (geom);
        CREATE INDEX tmp_distinct_pts_xy_idx ON tmp_distinct_pts (geocode_x, geocode_y);
        ANALYZE tmp_distinct_pts;

        CREATE TEMP TABLE tmp_sa_poly_sub AS
        SELECT
            id AS poly_id,
            layer_id,
            value,
            ST_Subdivide(
                CASE WHEN ST_IsValid(geom) THEN geom ELSE ST_CollectionExtract(ST_MakeValid(geom), 3) END,
                64
            ) AS geom
        FROM service_area_polygon
        WHERE geom IS NOT NULL;

        CREATE INDEX tmp_sa_poly_sub_gix ON tmp_sa_poly_sub USING GIST (geom);
        ANALYZE tmp_sa_poly_sub;
    """)
    db.save()

    # -------------------------------------------------------------------------
    # 2. Bulk PostGIS spatial join for all polygon service areas
    # -------------------------------------------------------------------------
    print("Running bulk PostGIS spatial join for polygon service areas...")
    col_names_sql = ", ".join(f'"{lid}"' for lid in sa_layer_ids)
    pivot_exprs_sql = ",\n            ".join(
        f"COALESCE(MAX(CASE WHEN layer_id = '{lid}' THEN agg_val END), '') AS \"{lid}\""
        for lid in sa_layer_ids
    )
    empty_fallback_sql = ", ".join(f"COALESCE(p.\"{lid}\", '')" for lid in sa_layer_ids)

    bulk_poly_sql = f"""
        WITH distinct_poly_hits AS (
            -- Deduplicate by poly_id so subdivided tiles of the same polygon only count once
            SELECT DISTINCT
                dp.geocode_x,
                dp.geocode_y,
                poly.poly_id,
                poly.layer_id,
                poly.value
            FROM tmp_distinct_pts dp
            JOIN tmp_sa_poly_sub poly
              ON ST_Intersects(poly.geom, dp.geom)
        ),
        pt_layer_vals AS (
            SELECT
                geocode_x,
                geocode_y,
                layer_id,
                string_agg(value, '|' ORDER BY value) AS agg_val
            FROM distinct_poly_hits
            GROUP BY geocode_x, geocode_y, layer_id
        ),
        pivoted AS (
            SELECT
                geocode_x,
                geocode_y,
                {pivot_exprs_sql}
            FROM pt_layer_vals
            GROUP BY geocode_x, geocode_y
        )
        INSERT INTO service_area_summary (street_address, {col_names_sql})
        SELECT
            ads.street_address,
            {empty_fallback_sql}
        FROM address_summary ads
        LEFT JOIN pivoted p
          ON ads.geocode_x = p.geocode_x AND ads.geocode_y = p.geocode_y;
    """
    db.execute(bulk_poly_sql)
    db.execute("DROP TABLE IF EXISTS tmp_sa_poly_sub;")
    db.save()

    # -------------------------------------------------------------------------
    # 3. Index service_area_summary & update line-based service areas
    # -------------------------------------------------------------------------
    print("Indexing service_area_summary and updating line-based service areas...")
    sa_summary_table = db["service_area_summary"]
    sa_summary_table.create_index("street_address")
    db.execute("""
        CREATE INDEX IF NOT EXISTS ix_address_summary_seg_id
            ON public.address_summary USING btree (seg_id);
        ANALYZE service_area_summary;
    """)
    db.save()

    for sa_layer_def in sa_layer_defs:
        layer_id = sa_layer_def["layer_id"]

        if "line_single" in sa_layer_def["sources"]:
            print(f"Updating line_single layer: {layer_id}...")
            db.execute(f"""
                UPDATE service_area_summary sas
                SET "{layer_id}" = sals.value
                FROM address_summary ads, service_area_line_single sals
                WHERE sas.street_address = ads.street_address
                  AND sals.seg_id = ads.seg_id
                  AND sals.layer_id = '{layer_id}'
                  AND sals.value <> '';
            """)
            db.save()

        elif "line_dual" in sa_layer_def["sources"]:
            print(f"Updating line_dual layer: {layer_id}...")
            db.execute(f"""
                UPDATE service_area_summary sas
                SET "{layer_id}" = CASE
                    WHEN ads.seg_side = 'L' THEN sald.left_value
                    ELSE sald.right_value
                END
                FROM address_summary ads, service_area_line_dual sald
                WHERE sas.street_address = ads.street_address
                  AND sald.seg_id = ads.seg_id
                  AND sald.layer_id = '{layer_id}'
                  AND (CASE WHEN ads.seg_side = 'L' THEN sald.left_value ELSE sald.right_value END) <> '';
            """)
            db.save()

    # -------------------------------------------------------------------------
    # 4. Service area points (GiST KNN over distinct points, or seg_id join)
    # -------------------------------------------------------------------------
    print("Updating point-based service areas...")
    for sa_layer_def in sa_layer_defs:
        layer_id = sa_layer_def["layer_id"]
        if "point" not in sa_layer_def["sources"]:
            continue
        method = sa_layer_def["sources"]["point"].get("method")
        if method == "nearest":
            print(f"Updating nearest point layer: {layer_id}...")
            db.execute(f"""
                DROP TABLE IF EXISTS tmp_knn_layer;
                CREATE TEMP TABLE tmp_knn_layer AS
                SELECT value, geom
                FROM service_area_point
                WHERE layer_id = '{layer_id}' AND geom IS NOT NULL;

                CREATE INDEX tmp_knn_layer_gix ON tmp_knn_layer USING GIST (geom);
                ANALYZE tmp_knn_layer;

                WITH pt_nearest AS (
                    SELECT dp.geocode_x, dp.geocode_y, knn.value
                    FROM tmp_distinct_pts dp
                    CROSS JOIN LATERAL (
                        SELECT l.value
                        FROM tmp_knn_layer l
                        ORDER BY dp.geom <-> l.geom
                        LIMIT 1
                    ) knn
                )
                UPDATE service_area_summary sas
                SET "{layer_id}" = pn.value
                FROM address_summary ads
                JOIN pt_nearest pn
                  ON ads.geocode_x = pn.geocode_x AND ads.geocode_y = pn.geocode_y
                WHERE sas.street_address = ads.street_address;

                DROP TABLE IF EXISTS tmp_knn_layer;
            """)
            db.save()

        elif method == "seg_id":
            print(f"Updating seg_id point layer: {layer_id}...")
            db.execute(f"""
                UPDATE service_area_summary sas
                SET "{layer_id}" = sap.value
                FROM address_summary ads, service_area_point sap
                WHERE sas.street_address = ads.street_address
                  AND sap.seg_id = ads.seg_id
                  AND sap.layer_id = '{layer_id}'
                  AND sap.value <> '';
            """)
            db.save()

    # -------------------------------------------------------------------------
    # 5. Nearest polygon layers (GiST KNN over distinct points)
    # -------------------------------------------------------------------------
    print("Updating nearest-polygon service areas...")
    for sa_layer_def in sa_layer_defs:
        layer_id = sa_layer_def["layer_id"]
        if "polygon" not in sa_layer_def["sources"]:
            continue
        if sa_layer_def["sources"]["polygon"].get("method") != "nearest_poly":
            continue
        print(f"Updating nearest_poly layer: {layer_id}...")
        db.execute(f"""
            DROP TABLE IF EXISTS tmp_knn_layer;
            CREATE TEMP TABLE tmp_knn_layer AS
            SELECT value, geom
            FROM service_area_polygon
            WHERE layer_id = '{layer_id}' AND geom IS NOT NULL;

            CREATE INDEX tmp_knn_layer_gix ON tmp_knn_layer USING GIST (geom);
            ANALYZE tmp_knn_layer;

            WITH pt_nearest AS (
                SELECT dp.geocode_x, dp.geocode_y, knn.value
                FROM tmp_distinct_pts dp
                CROSS JOIN LATERAL (
                    SELECT l.value
                    FROM tmp_knn_layer l
                    ORDER BY dp.geom <-> l.geom
                    LIMIT 1
                ) knn
            )
            UPDATE service_area_summary sas
            SET "{layer_id}" = pn.value
            FROM address_summary ads
            JOIN pt_nearest pn
              ON ads.geocode_x = pn.geocode_x AND ads.geocode_y = pn.geocode_y
            WHERE sas.street_address = ads.street_address;

            DROP TABLE IF EXISTS tmp_knn_layer;
        """)
        db.save()

    db.execute("DROP TABLE IF EXISTS tmp_distinct_pts;")
    db.save()

    # -------------------------------------------------------------------------
    # 6. Yes/No normalization (single table scan)
    # -------------------------------------------------------------------------
    yes_no_layers = [
        d["layer_id"] for d in sa_layer_defs if d.get("value_method") == "yes_or_no"
    ]
    if yes_no_layers:
        print(f"Normalizing {len(yes_no_layers)} yes_or_no layer(s)...")
        set_clauses = ", ".join(
            f"\"{lid}\" = CASE WHEN \"{lid}\" != '' THEN 'Yes' ELSE 'No' END"
            for lid in yes_no_layers
        )
        db.execute(f"UPDATE service_area_summary SET {set_clauses};")
        db.save()

    # -------------------------------------------------------------------------
    # 7. Backfill missing zip_codes & ensure all required address_summary indexes
    # -------------------------------------------------------------------------
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
    db.close()

    print(f"Finished make_service_area_summary in {datetime.now() - start}")
