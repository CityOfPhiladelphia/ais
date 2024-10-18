import subprocess
import pytest
import os
from ais import app
import psycopg2
from psycopg2.extras import RealDictCursor
# Loads flask vars from ais/instance/config.py
config = app.config


@pytest.fixture
def startup():
    """Startup fixture: make database connections and define tables to ignore"""
    def db_cursor(**creds):
        conn = psycopg2.connect(**creds)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        return cursor

    # Get our current directory
    proc = subprocess.Popen(['bash', '-c', 'pwd'], stdout=subprocess.PIPE)
    output = proc.stdout.read()
    working_dir = output.rstrip()
    working_dir = working_dir.decode('utf-8')
    print("Current working directly is: " + working_dir)

    engine_to_test = os.environ.get('ENGINE_TO_TEST', None)
    engine_to_compare = os.environ.get('ENGINE_TO_COMPARE', None)

    print(f'running tests against {engine_to_test} and comparing against {engine_to_compare}')

    # Get full creds based on RDS CNAME passed to us
    if 'blue' in engine_to_compare:
        engine_to_compare_cur = db_cursor(**config["BLUE_DATABASE"])
    elif 'green' in engine_to_compare:
        engine_to_compare_cur = db_cursor(**config["GREEN_DATABASE"])

    if engine_to_test == 'localhost':
        engine_to_test_cur = db_cursor(**config["LOCAL_BUILD_DATABASE"])
    else:
        # Get full creds based on RDS CNAME passed to us
        if 'blue' in engine_to_test:
            engine_to_test_cur = db_cursor(**config["BLUE_DATABASE"])
        elif 'green' in engine_to_test:
            engine_to_test_cur = db_cursor(**config["GREEN_DATABASE"])

    unused_tables =  ('spatial_ref_sys', 'alembic_version', 'multiple_seg_line', 'service_area_diff', 'address_zip', 'zip_range', 'dor_parcel_address_analysis', 'address_summary_transformed')
    changed_tables = ('ng911_address_point',)
    ignore_tables = unused_tables + changed_tables

    return {'engine_to_test_cur': engine_to_test_cur,
            'engine_to_compare_cur': engine_to_compare_cur,
            'unused_tables': unused_tables,
            'changed_tables': changed_tables,
            'ignore_tables': ignore_tables}

def test_no_duplicates(startup):
    """ Don't allow duplicate street_addresses in address_summary """

    engine_to_test_cur = startup['engine_to_test_cur']
    total_stmt = "select count(*) as total_addresses from address_summary"
    distinct_stmt = "select count(*) as distinct_addresses from (select distinct street_address from address_summary) foo"
    engine_to_test_cur.execute(total_stmt)
    num_total_row = engine_to_test_cur.fetchall()

    engine_to_test_cur.execute(distinct_stmt)
    num_distinct_row = engine_to_test_cur.fetchall()

    num_total = num_total_row[0]['total_addresses']
    num_distinct = num_distinct_row[0]['distinct_addresses']
    assert num_total == num_distinct


def test_compare_num_tables(startup):
    """Test #1: Check if all tables are included in build"""
    # assert len(startup['engine_to_test_cur'].tables) == len(startup['engine_to_compare_cur'].tables)
    engine_to_test_cur = startup['engine_to_test_cur']
    engine_to_compare_cur = startup['engine_to_compare_cur']
    table_count_stmt = "select count(*) from information_schema.tables where table_schema = 'public' AND table_type = 'BASE TABLE' and table_name not in {}".format(str(startup['ignore_tables']))
    engine_to_test_cur.execute(table_count_stmt)
    new_table_count = engine_to_test_cur.fetchall()

    engine_to_compare_cur.execute(table_count_stmt)
    old_table_count = engine_to_compare_cur.fetchall()
    assert new_table_count == old_table_count

#@pytest.mark.skip(reason="temp change of eclipse_location_ids source table with more rows")
def test_num_rows_bt_db_tables(startup):
    """"Test #2: Check if all tables within 10% of rows as old version"""
    engine_to_test_cur = startup['engine_to_test_cur']
    engine_to_compare_cur = startup['engine_to_compare_cur']
    list_tables_stmt = "select table_name from information_schema.tables where table_schema = 'public' AND table_type = 'BASE TABLE'"
    engine_to_test_cur.execute(list_tables_stmt)
    engine_to_test_cur_tables = engine_to_test_cur.fetchall()

    engine_to_compare_cur.execute(list_tables_stmt)
    engine_to_compare_cur_tables = engine_to_compare_cur.fetchall()
    # engine_to_test_cur_tables = startup['engine_to_test_cur'].tables
    for ntable in engine_to_test_cur_tables:
        table_name = ntable['table_name']
        if table_name in startup['ignore_tables']:
            continue

        # ndb_table = startup['engine_to_test_cur'][ntable]
        # n_rows = ndb_table.count
        row_count_stmt = "select count(*) as count from {}".format(table_name)
        engine_to_test_cur.execute(row_count_stmt)
        n_rows = engine_to_test_cur.fetchall()

        engine_to_compare_cur.execute(row_count_stmt)
        o_rows = engine_to_compare_cur.fetchall()
        # odb_table = startup['engine_to_compare_cur'][ntable]
        # o_rows = odb_table.count
        fdif = abs((n_rows[0]['count'] - o_rows[0]['count']) / o_rows[0]['count'])

        print('Making sure percent of rows that have changed are less than a 10% threshold')
        assert fdif <= 0.1, (ntable, fdif)


#@pytest.mark.skip(reason="added geocode type for ng911")
def test_geocode_types(startup):
    """Test #3: Check if all geocode types present (compare new an old builds)"""
    engine_to_test_cur = startup['engine_to_test_cur']
    engine_to_compare_cur = startup['engine_to_compare_cur']

    def get_geo_types(db):
        stmt = "SELECT DISTINCT geocode_type FROM geocode"
        db.execute(stmt)
        geo_types = db.fetchall()
        results = sorted([f['geocode_type'] for f in geo_types])

        return results

    n_geo_types = get_geo_types(engine_to_test_cur)
    o_geo_types = get_geo_types(engine_to_compare_cur)

    assert n_geo_types == o_geo_types


def test_matching_indexes(startup):
    """Test #4: Check if all indexes are present (compare new an old builds)"""
    stmt = '''
        SELECT n.nspname as "Schema",
          c.relname as "Name",
          CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view' WHEN 'i'
        THEN 'index' WHEN 'S' THEN 'sequence' WHEN 's' THEN 'special' END as "Type",
          u.usename as "Owner",
         c2.relname as "Table"
        FROM pg_catalog.pg_class c
             JOIN pg_catalog.pg_index i ON i.indexrelid = c.oid
             JOIN pg_catalog.pg_class c2 ON i.indrelid = c2.oid
             LEFT JOIN pg_catalog.pg_user u ON u.usesysid = c.relowner
             LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('i','')
              AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
              AND pg_catalog.pg_table_is_visible(c.oid)
              AND c2.relname NOT IN {ignore_tables}
        ORDER BY 1,2;
    '''.format(ignore_tables=startup['unused_tables'])
    startup['engine_to_test_cur'].execute(stmt)
    engine_to_test_cur_result = startup['engine_to_test_cur'].fetchall()
    startup['engine_to_compare_cur'].execute(stmt)
    engine_to_compare_cur_result = startup['engine_to_compare_cur'].fetchall()

    unmatched_indexes = []
    for old_row in engine_to_compare_cur_result:
        #assert 1 == 2, (old_row, dir(old_row), old_row.items())
        found = False
        if found: continue
        for new_row in engine_to_test_cur_result:
            if new_row['Name'] == old_row['Name']:
                found = True
                break
        if not found:
            unmatched_indexes.append({'name': old_row['Name'], 'table': old_row['Table']})
    assert len(unmatched_indexes) == 0, (unmatched_indexes)
    # assert len(engine_to_test_cur_result) == len(engine_to_compare_cur_result), (
    # "new db has {} more indexes.".format(len(engine_to_test_cur_result) - len(engine_to_compare_cur_result)))


def test_num_opa_records(startup):
    opa_property_row_count_for_testing = 583900
    stmt = '''select count(*) as num_rows from opa_property;'''
    startup['engine_to_test_cur'].execute(stmt)
    num_opa_property_rows = startup['engine_to_test_cur'].fetchall()[0]['num_rows']
    assert num_opa_property_rows > opa_property_row_count_for_testing


@pytest.fixture(scope="module")
def teardown():
    """Teardown fixture: close db connections"""
    engine_to_test_cur = startup['engine_to_test_cur']
    engine_to_compare_cur = startup['engine_to_compare_cur']
    yield
    engine_to_test_cur.close()
    engine_to_compare_cur.close()
    return (engine_to_test_cur, engine_to_compare_cur)


