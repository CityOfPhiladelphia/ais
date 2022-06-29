import subprocess
import pytest
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

    proc = subprocess.Popen(['bash', '-c', 'pwd'], stdout=subprocess.PIPE)
    output = proc.stdout.read()
    prod_env_color = output.rstrip()
    prod_env_color = prod_env_color.decode('utf-8')
    print("Working directory: " + prod_env_color)

    # Get prod color
    proc = subprocess.Popen(['bash', '-c', '. ./ais/engine/bin/ais-utils.sh; get_prod_env'],
            stdout=subprocess.PIPE)
    # format the stdout we got properly into a simple string
    output = proc.stdout.read()
    prod_env_color = output.rstrip()
    prod_env_color = prod_env_color.decode('utf-8')



    if prod_env_color == 'blue':
        prod_rds_db_cur = db_cursor(**config["BLUE_DATABASE"])
    elif prod_env_color == 'green':
        prod_rds_db_cur = db_cursor(**config["GREEN_DATABASE"])
    else:
        raise AssertionError(f'prod_env_color not expected value?: {prod_env_color}')
        

    local_build_db_cur = db_cursor(**config["LOCAL_BUILD_DATABASE"])

    unused_tables =  ('spatial_ref_sys', 'alembic_version', 'multiple_seg_line', 'service_area_diff', 'address_zip', 'zip_range', 'dor_parcel_address_analysis', 'address_summary_transformed')
    changed_tables = ()
    ignore_tables = unused_tables + changed_tables

    # local_build_db_cur = local
    # prod_rds_db_cur = prod_rds
    return {'local_build_db_cur': local_build_db_cur,
            'prod_rds_db_cur': prod_rds_db_cur,
            'unused_tables': unused_tables,
            'changed_tables': changed_tables,
            'ignore_tables': ignore_tables}

def test_no_duplicates(startup):
    """ Don't allow duplicate street_addresses in address_summary """

    local_build_db_cur = startup['local_build_db_cur']
    total_stmt = "select count(*) as total_addresses from address_summary"
    distinct_stmt = "select count(*) as distinct_addresses from (select distinct street_address from address_summary) foo"
    local_build_db_cur.execute(total_stmt)
    num_total_row = local_build_db_cur.fetchall()

    local_build_db_cur.execute(distinct_stmt)
    num_distinct_row = local_build_db_cur.fetchall()

    num_total = num_total_row[0]['total_addresses']
    num_distinct = num_distinct_row[0]['distinct_addresses']
    assert num_total == num_distinct


def test_compare_num_tables(startup):
    """Test #1: Check if all tables are included in build"""
    # assert len(startup['local_build_db_cur'].tables) == len(startup['prod_rds_db_cur'].tables)
    local_build_db_cur = startup['local_build_db_cur']
    prod_rds_db_cur = startup['prod_rds_db_cur']
    table_count_stmt = "select count(*) from information_schema.tables where table_schema = 'public' AND table_type = 'BASE TABLE' AND table_name NOT IN {}".format(startup['ignore_tables'])
    local_build_db_cur.execute(table_count_stmt)
    new_table_count = local_build_db_cur.fetchall()

    prod_rds_db_cur.execute(table_count_stmt)
    old_table_count = prod_rds_db_cur.fetchall()
    assert new_table_count == old_table_count

#@pytest.mark.skip(reason="temp change of eclipse_location_ids source table with more rows")
def test_num_rows_bt_db_tables(startup):
    """"Test #2: Check if all tables within 10% of rows as old version"""
    local_build_db_cur = startup['local_build_db_cur']
    prod_rds_db_cur = startup['prod_rds_db_cur']
    list_tables_stmt = "select table_name from information_schema.tables where table_schema = 'public' AND table_type = 'BASE TABLE'"
    local_build_db_cur.execute(list_tables_stmt)
    local_build_db_cur_tables = local_build_db_cur.fetchall()
    print("DEBUG1!!!!!: ", str(local_build_db_cur_tables))

    prod_rds_db_cur.execute(list_tables_stmt)
    prod_rds_db_cur_tables = prod_rds_db_cur.fetchall()
    # local_build_db_cur_tables = startup['local_build_db_cur'].tables
    print("DEBUG1!!!!!: ", str(prod_rds_db_cur_tables))
    for ntable in local_build_db_cur_tables:
        table_name = ntable['table_name']
        if table_name in startup['ignore_tables']:
            continue

        # ndb_table = startup['local_build_db_cur'][ntable]
        # n_rows = ndb_table.count
        row_count_stmt = "select count(*) as count from {}".format(table_name)
        local_build_db_cur.execute(row_count_stmt)
        n_rows = local_build_db_cur.fetchall()

        prod_rds_db_cur.execute(row_count_stmt)
        o_rows = prod_rds_db_cur.fetchall()
        # odb_table = startup['prod_rds_db_cur'][ntable]
        # o_rows = odb_table.count
        fdif = abs((n_rows[0]['count'] - o_rows[0]['count']) / o_rows[0]['count'])

        assert fdif <= 0.1, (ntable, fdif)


def test_geocode_types(startup):
    """Test #3: Check if all geocode types present (compare new an old builds)"""
    local_build_db_cur = startup['local_build_db_cur']
    prod_rds_db_cur = startup['prod_rds_db_cur']

    def get_geo_types(db):
        stmt = "SELECT DISTINCT geocode_type FROM geocode"
        db.execute(stmt)
        geo_types = db.fetchall()
        results = sorted([f['geocode_type'] for f in geo_types])

        return results

    n_geo_types = get_geo_types(local_build_db_cur)
    o_geo_types = get_geo_types(prod_rds_db_cur)

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
    startup['local_build_db_cur'].execute(stmt)
    local_build_db_cur_result = startup['local_build_db_cur'].fetchall()
    startup['prod_rds_db_cur'].execute(stmt)
    prod_rds_db_cur_result = startup['prod_rds_db_cur'].fetchall()

    unmatched_indexes = []
    for old_row in prod_rds_db_cur_result:
        #assert 1 == 2, (old_row, dir(old_row), old_row.items())
        found = False
        if found: continue
        for new_row in local_build_db_cur_result:
            if new_row['Name'] == old_row['Name']:
                found = True
                break
        if not found:
            unmatched_indexes.append({'name': old_row['Name'], 'table': old_row['Table']})
    assert len(unmatched_indexes) == 0, (unmatched_indexes)
    # assert len(local_build_db_cur_result) == len(prod_rds_db_cur_result), (
    # "new db has {} more indexes.".format(len(local_build_db_cur_result) - len(prod_rds_db_cur_result)))


@pytest.fixture(scope="module")
def teardown():
    """Teardown fixture: close db connections"""
    local_build_db_cur = startup['local_build_db_cur']
    prod_rds_db_cur = startup['prod_rds_db_cur']
    yield
    local_build_db_cur.close()
    prod_rds_db_cur.close()
    return (local_build_db_cur, prod_rds_db_cur)


