"""Build the denormalized `address_summary` table.

Performance improvements over the legacy version:
- Loads `address_tag` in a single bulk scan (replaces 3,500+ per-street SQL subqueries).
- Pre-groups tags by `(street_address, key)` for O(1) lookup.
- Uses shallow `dict(row)` instead of 600,000 `deepcopy()` calls.
- Uses a `set` for `ungeocoded_opa_addresses` and a reverse dict for `geocode_priority`.
- Removes unused `address_link` full-table read.
- Inserts ungeocoded OPA addresses into `geocode` in one bulk SQL statement.
"""

from datetime import datetime
from ais import app
from ais.engine.db import connect


def _wkt_to_xy(wkt: str) -> tuple[float, float]:
    xy = wkt.replace("POINT(", "").replace(")", "").split(" ")
    return float(xy[0]), float(xy[1])


def main():
    print("Starting make_address_summary...")
    start = datetime.now()

    config = app.config
    db = connect(config["DATABASES"]["engine"])
    tag_fields = config["ADDRESS_SUMMARY"]["tag_fields"]
    non_summary_tags = set(config["ADDRESS_SUMMARY"]["non_summary_tags"])
    geocode_types = config["ADDRESS_SUMMARY"]["geocode_types"]
    geocode_priority_map = config["ADDRESS_SUMMARY"]["geocode_priority"]
    reverse_priority_map = {v: k for k, v in geocode_priority_map.items()}
    geocode_types_in_street = config["ADDRESS_SUMMARY"]["geocode_types_in_street"]

    geocode_table = db["geocode"]
    address_table = db["address"]
    address_summary_table = db["address_summary"]

    active_tag_fields = [tf for tf in tag_fields if tf["name"] not in non_summary_tags]
    active_tag_keys = {tf["tag_key"] for tf in active_tag_fields}

    print("Dropping indexes and clearing address_summary...")
    address_summary_table.drop_index("street_address")
    db.execute("DROP INDEX IF EXISTS address_summary_opa_owners_trigram_idx;")
    db.save()
    address_summary_table.delete()

    print("Reading geocodes...")
    geocode_map: dict[str, dict[str, str]] = {}
    for row in geocode_table.read(fields=["street_address", "geocode_type"], geom_field="geom"):
        gt_str = reverse_priority_map[row["geocode_type"]]
        geocode_map.setdefault(row["street_address"], {})[gt_str] = row["geom"]

    print("Reading ungeocoded OPA addresses...")
    ungeocoded_opa_addresses = {
        row["street_address"]
        for row in db.execute(
            "SELECT street_address FROM opa_property EXCEPT SELECT street_address FROM geocode"
        )
    }

    print("Reading unit children ('has generic unit')...")
    unit_child_map: dict[str, list[str]] = {}
    unit_children_set: set[str] = set()
    for row in db.execute(
        "SELECT address_1, address_2 FROM address_link WHERE relationship = 'has generic unit'"
    ):
        child_addr = row["address_1"]
        parent_addr = row["address_2"]
        unit_child_map.setdefault(parent_addr, []).append(child_addr)
        unit_children_set.add(child_addr)

    print("Reading all address tags in a single scan...")
    # tag_map[street_address][tag_key] = [(street_address, upper_value), ...]
    tag_map: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for row in db.execute("SELECT street_address, key, value FROM address_tag"):
        key = row["key"]
        if key not in active_tag_keys:
            continue
        val = row["value"]
        if not val:
            continue
        addr = row["street_address"]
        tag_map.setdefault(addr, {}).setdefault(key, []).append((addr, val.upper()))

    print("Building address summary rows...")
    address_rows = address_table.read()
    summary_rows: list[dict] = []
    geocode_errors = 0

    for address_row in address_rows:
        street_address = address_row["street_address"]
        if street_address in unit_children_set:
            continue

        # Check geocodes early so we skip ungeocoded non-OPA addresses before tag work
        xy_map = geocode_map.get(street_address)
        if not xy_map:
            geocode_errors += 1

        geocode_vals = None
        if xy_map:
            for gt in geocode_types:
                if gt in xy_map:
                    x, y = _wkt_to_xy(xy_map[gt])
                    geocode_vals = {
                        "geocode_type": gt,
                        "geocode_x": x,
                        "geocode_y": y,
                        "geocode_street_x": None,
                        "geocode_street_y": None,
                    }
                    break
            if geocode_vals is not None:
                for gt in geocode_types_in_street:
                    if gt in xy_map:
                        sx, sy = _wkt_to_xy(xy_map[gt])
                        geocode_vals["geocode_street_x"] = sx
                        geocode_vals["geocode_street_y"] = sy
                        break
        if geocode_vals is None:
            if street_address in ungeocoded_opa_addresses:
                geocode_vals = {
                    "geocode_type": "unable_to_geocode",
                    "geocode_x": None,
                    "geocode_y": None,
                    "geocode_street_x": None,
                    "geocode_street_y": None,
                }
            else:
                continue

        summary_row = dict(address_row)
        addr_tags = tag_map.get(street_address)
        unit_children = unit_child_map.get(street_address)

        for tag_field in active_tag_fields:
            field_name = tag_field["name"]
            tag_key = tag_field["tag_key"]
            field_type = tag_field["type"]

            pairs = list(addr_tags.get(tag_key, ())) if addr_tags else []
            if unit_children and addr_tags is not None:
                for uc in unit_children:
                    uc_tags = tag_map.get(uc)
                    if uc_tags and tag_key in uc_tags:
                        pairs.extend(uc_tags[tag_key])

            if pairs:
                if "usps" in tag_key:
                    non_pound_val = ""
                    generic_usps_val = ""
                    seen_addrs: set[str] = set()
                    for t_addr, t_val in pairs:
                        if t_addr in seen_addrs:
                            continue
                        seen_addrs.add(t_addr)
                        if "#" not in t_addr:
                            non_pound_val = t_val
                        else:
                            generic_usps_val = t_val
                    value = non_pound_val or generic_usps_val
                else:
                    unique_vals = sorted({v for _, v in pairs})
                    value = "|".join(unique_vals)[:2000]
            else:
                value = None if field_type == "number" else ""

            summary_row[field_name] = value

        summary_row.update(geocode_vals)
        summary_rows.append(summary_row)

    print(f"Writing {len(summary_rows)} summary rows...")
    address_summary_table.write(summary_rows, chunk_size=100000)
    del summary_rows

    print("Creating indexes...")
    address_summary_table.create_index("street_address")
    db.execute("""
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE INDEX address_summary_opa_owners_trigram_idx
            ON address_summary USING GIN (opa_owners gin_trgm_ops);
    """)
    db.save()

    print("Populating seg IDs...")
    db.execute("""
        UPDATE address_summary asm
        SET seg_id = ast.seg_id, seg_side = ast.seg_side
        FROM address_street ast
        WHERE ast.street_address = asm.street_address
    """)
    db.save()

    print("Populating street codes...")
    db.execute("""
        UPDATE address_summary asm
        SET street_code = sts.street_code
        FROM street_segment sts
        WHERE sts.seg_id = asm.seg_id
    """)
    db.save()

    # Update street codes for ranged addresses with overlapping street segs
    db.execute("""
        WITH scnulls AS (
            SELECT street_address, address_low, address_low_suffix, address_low_frac,
                   street_predir, street_name, street_suffix, street_postdir
            FROM address_summary
            WHERE street_code IS NULL AND address_high IS NOT NULL
        )
        UPDATE address_summary asm
        SET street_code = final.street_code
        FROM (
            SELECT s.street_address, asmj.street_code
            FROM scnulls s
            INNER JOIN address_summary asmj
              ON asmj.street_code IS NOT NULL
             AND asmj.address_low = s.address_low
             AND asmj.address_low_suffix = s.address_low_suffix
             AND asmj.address_low_frac = s.address_low_frac
             AND s.street_predir = asmj.street_predir
             AND s.street_name = asmj.street_name
             AND asmj.street_suffix = s.street_suffix
             AND asmj.street_postdir = s.street_postdir
            GROUP BY s.street_address, asmj.street_code
        ) final
        WHERE final.street_address = asm.street_address
    """)
    db.save()

    print("Populating OPA accounts...")
    db.execute("""
        UPDATE address_summary asm
        SET opa_account_num = op.account_num,
            opa_owners = op.owners,
            opa_address = op.street_address
        FROM address_property ap, opa_property op
        WHERE asm.street_address = ap.street_address
          AND ap.opa_account_num = op.account_num
    """)
    db.save()

    print("Populating li_parcel_id...")
    db.execute("""
        WITH bpis AS (
            SELECT street_address, MAX(value) AS bin_parcel_id
            FROM address_tag
            WHERE key = 'bin_parcel_id'
            GROUP BY street_address
        ),
        pwd_parcel_ids AS (
            SELECT asum.street_address, split_part(asum.pwd_parcel_id, '|', 1) AS pwd_parcel_id
            FROM address_summary asum
            INNER JOIN pwd_parcel pp
              ON split_part(asum.pwd_parcel_id, '|', 1) = pp.parcel_id::text
        ),
        opa_account_nums AS (
            SELECT op.street_address, op.account_num AS opa_account_num
            FROM opa_property op
            INNER JOIN address_summary asum ON asum.street_address = op.street_address
        ),
        choices AS (
            SELECT DISTINCT asum.street_address, ppis.pwd_parcel_id, ops.opa_account_num, bpis.bin_parcel_id
            FROM address_summary asum
            LEFT JOIN bpis ON bpis.street_address = asum.street_address
            LEFT JOIN pwd_parcel_ids ppis ON ppis.street_address = asum.street_address
            LEFT JOIN opa_account_nums ops ON ops.street_address = asum.street_address
        ),
        address_sources AS (
            SELECT street_address, string_agg(source_name, '|' ORDER BY source_name) AS sources
            FROM (
                SELECT DISTINCT street_address, source_name
                FROM source_address
                WHERE source_name NOT IN (
                    'AIS', 'voters', 'info_commercial', 'info_residents',
                    'li_eclipse_location_ids', 'li_address_keys'
                )
            ) foo
            GROUP BY street_address
        ),
        final AS (
            SELECT ch.street_address,
                CASE
                    WHEN ch.pwd_parcel_id != '' THEN ch.pwd_parcel_id
                    WHEN ch.bin_parcel_id != '' THEN ch.bin_parcel_id
                    WHEN ch.opa_account_num != '' THEN '-' || ch.opa_account_num
                    ELSE ''
                END AS li_parcel_id,
                s.sources
            FROM choices ch
            LEFT JOIN address_sources s ON s.street_address = ch.street_address
        )
        UPDATE address_summary asm
        SET li_parcel_id = final.li_parcel_id
        FROM final
        WHERE final.street_address = asm.street_address
          AND final.sources IS NOT NULL
    """)
    db.save()

    print("Inserting ungeocoded OPA addresses into geocode table in bulk...")
    db.execute("""
        INSERT INTO geocode (street_address, geocode_type)
        SELECT street_address, 99
        FROM (
            SELECT street_address FROM opa_property
            EXCEPT
            SELECT street_address FROM geocode
        ) ungeocoded
    """)
    db.save()
    db.close()

    print(f"{geocode_errors} geocode errors")
    print(f"Finished make_address_summary in {datetime.now() - start}")
