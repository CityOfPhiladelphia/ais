"""Propagate parcel geocodes across linked addresses in a single bulk SQL query.

Replaces the legacy Python script that loaded the entire geocode & address_tag
tables into RAM and issued string-concatenated INSERT statements.
"""

from datetime import datetime
from ais import app
from ais.engine.db import connect


def main():
    start = datetime.now()
    print("Starting geocode_addresses_from_links...")

    config = app.config
    db = connect(config["DATABASES"]["engine"])
    geocode_table = db["geocode"]

    print("Dropping geocode(street_address) index before bulk insert...")
    # Keep index during SELECT, or use a temp table? Creating a temp table
    # while the index is still present makes the JOIN/NOT EXISTS super fast,
    # then we drop the index, insert, and rebuild once!
    print("Computing linked geocodes in PostgreSQL...")
    db.execute("""
        CREATE TEMP TABLE tmp_linked_geocodes AS
        WITH linked_tags AS (
            SELECT DISTINCT street_address, linked_address, key
            FROM address_tag
            WHERE linked_address IS NOT NULL
              AND linked_address != ''
              AND key IN ('pwd_parcel_id', 'dor_parcel_id')
        )
        SELECT DISTINCT
            lt.street_address,
            g.geocode_type,
            g.geom
        FROM linked_tags lt
        JOIN geocode g
          ON g.street_address = lt.linked_address
        WHERE (
            lt.key = 'pwd_parcel_id'
            AND g.geocode_type IN (1, 3, 7, 11)
            AND NOT EXISTS (
                SELECT 1 FROM geocode existing
                WHERE existing.street_address = lt.street_address
                  AND existing.geocode_type = 1
            )
        )
        OR (
            lt.key = 'dor_parcel_id'
            AND g.geocode_type IN (2, 4, 8, 12)
            AND NOT EXISTS (
                SELECT 1 FROM geocode existing
                WHERE existing.street_address = lt.street_address
                  AND existing.geocode_type = 2
            )
        );
    """)

    geocode_table.drop_index("street_address")

    print("Inserting linked geocodes into geocode table...")
    db.execute("""
        INSERT INTO geocode (street_address, geocode_type, geom)
        SELECT street_address, geocode_type, geom
        FROM tmp_linked_geocodes;
    """)
    db.execute("DROP TABLE IF EXISTS tmp_linked_geocodes;")
    db.save()

    print("Rebuilding index on geocode(street_address)...")
    geocode_table.create_index("street_address")
    db.close()
    print(f"Finished geocode_addresses_from_links in {datetime.now() - start}")
