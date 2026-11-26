"""Engine database validation tests comparing a candidate build against production."""

import os
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from ais import app
from ais.util import unwrap_secret

config = app.config

UNUSED_TABLES = (
    "spatial_ref_sys",
    "alembic_version",
    "multiple_seg_line",
    "service_area_diff",
    "address_zip",
    "zip_range",
    "dor_parcel_address_analysis",
    "address_summary_transformed",
)


def _resolve_db_creds(target: str) -> dict:
    """Resolve psycopg2 connection kwargs from host string or alias."""
    if not target:
        raise RuntimeError("ENGINE_TO_TEST and ENGINE_TO_COMPARE must be set")
    lowered = target.lower()
    if lowered == "localhost":
        creds = dict(config["LOCAL_BUILD_DATABASE"])
    elif "blue" in lowered:
        creds = dict(config["BLUE_DATABASE"])
    elif "green" in lowered:
        creds = dict(config["GREEN_DATABASE"])
    else:
        creds = {
            "user": os.environ.get("RDS_ENGINE_DB_USER", "ais_engine"),
            "host": target,
            "password": os.environ.get("RDS_ENGINE_DB_PASS") or os.environ.get("ENGINE_DB_PASS", ""),
            "dbname": os.environ.get("RDS_ENGINE_DB_NAME", "ais_engine"),
        }
    creds["password"] = unwrap_secret(creds.get("password"))
    return creds


@pytest.fixture(scope="module")
def startup():
    """Open cursors to the candidate engine DB and the reference comparison DB."""
    engine_to_test = os.environ.get("ENGINE_TO_TEST")
    engine_to_compare = os.environ.get("ENGINE_TO_COMPARE")
    print(f"Testing {engine_to_test} against {engine_to_compare}")

    test_conn = psycopg2.connect(**_resolve_db_creds(engine_to_test))
    compare_conn = psycopg2.connect(**_resolve_db_creds(engine_to_compare))
    test_cur = test_conn.cursor(cursor_factory=RealDictCursor)
    compare_cur = compare_conn.cursor(cursor_factory=RealDictCursor)

    try:
        yield {
            "engine_to_test_cur": test_cur,
            "engine_to_compare_cur": compare_cur,
            "unused_tables": UNUSED_TABLES,
            "changed_tables": (),
            "ignore_tables": UNUSED_TABLES,
        }
    finally:
        test_cur.close()
        compare_cur.close()
        test_conn.close()
        compare_conn.close()


def test_no_duplicates(startup):
    """Don't allow duplicate street_addresses in address_summary."""
    cur = startup["engine_to_test_cur"]
    cur.execute("SELECT count(*) AS total_addresses FROM address_summary")
    num_total = cur.fetchone()["total_addresses"]

    cur.execute("SELECT count(DISTINCT street_address) AS distinct_addresses FROM address_summary")
    num_distinct = cur.fetchone()["distinct_addresses"]
    assert num_total == num_distinct


def test_compare_num_tables(startup):
    """Check that all expected tables are present in the build."""
    stmt = (
        "SELECT count(*) AS cnt FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "AND table_name <> ALL(%s)"
    )
    ignore = list(startup["ignore_tables"])
    startup["engine_to_test_cur"].execute(stmt, (ignore,))
    new_count = startup["engine_to_test_cur"].fetchone()["cnt"]

    startup["engine_to_compare_cur"].execute(stmt, (ignore,))
    old_count = startup["engine_to_compare_cur"].fetchone()["cnt"]
    assert new_count == old_count


def test_num_rows_bt_db_tables(startup):
    """Check that every table row count is within 10% of the reference DB."""
    list_tables_stmt = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    test_cur = startup["engine_to_test_cur"]
    compare_cur = startup["engine_to_compare_cur"]

    test_cur.execute(list_tables_stmt)
    tables = [row["table_name"] for row in test_cur.fetchall()]

    for table_name in tables:
        if table_name in startup["ignore_tables"]:
            continue

        row_count_stmt = f'SELECT count(*) AS count FROM "{table_name}"'
        test_cur.execute(row_count_stmt)
        n_rows = test_cur.fetchone()["count"]

        compare_cur.execute(row_count_stmt)
        o_rows = compare_cur.fetchone()["count"]

        if o_rows == 0:
            assert n_rows == 0, (table_name, n_rows, o_rows)
        else:
            fdif = abs((n_rows - o_rows) / o_rows)
            assert fdif <= 0.1, (table_name, fdif, n_rows, o_rows)


def test_geocode_types(startup):
    """Check that all geocode types match between candidate and reference builds."""
    def get_geo_types(cur):
        cur.execute("SELECT DISTINCT geocode_type FROM geocode")
        return sorted(row["geocode_type"] for row in cur.fetchall())

    assert get_geo_types(startup["engine_to_test_cur"]) == get_geo_types(
        startup["engine_to_compare_cur"]
    )


def test_matching_indexes(startup):
    """Check that all indexes from the reference build exist in the candidate build."""
    stmt = """
        SELECT c.relname AS "Name", c2.relname AS "Table"
        FROM pg_catalog.pg_class c
             JOIN pg_catalog.pg_index i ON i.indexrelid = c.oid
             JOIN pg_catalog.pg_class c2 ON i.indrelid = c2.oid
             LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('i', '')
              AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
              AND pg_catalog.pg_table_is_visible(c.oid)
              AND c2.relname <> ALL(%s)
        ORDER BY 1, 2
    """
    ignore = list(startup["unused_tables"])
    startup["engine_to_test_cur"].execute(stmt, (ignore,))
    new_names = {row["Name"] for row in startup["engine_to_test_cur"].fetchall()}

    startup["engine_to_compare_cur"].execute(stmt, (ignore,))
    old_rows = startup["engine_to_compare_cur"].fetchall()

    unmatched = [
        {"name": row["Name"], "table": row["Table"]}
        for row in old_rows
        if row["Name"] not in new_names
    ]
    assert len(unmatched) == 0, unmatched


def test_num_opa_records(startup):
    """Verify opa_property meets minimum expected row threshold."""
    startup["engine_to_test_cur"].execute("SELECT count(*) AS num_rows FROM opa_property")
    num_rows = startup["engine_to_test_cur"].fetchone()["num_rows"]
    assert num_rows > 580000
