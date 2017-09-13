import subprocess
import datum
import pytest
from ais import app
config = app.config
db = datum.connect(config['DATABASES']['engine'])

@pytest.fixture
def startup():
    """Startup fixture: make database connections and define tables to ignore"""
    new_db_map = {
        'ais-api-broad':     'engine_broad',
        'ais-api-market':    'engine_market',
    }
    proc = subprocess.Popen(['bash', '-c', '. ../../../bin/eb_env_utils.sh; get_prod_env'], stdout=subprocess.PIPE)
    output = proc.stdout.read()
    old_prod_env = output.rstrip()
    old_prod_env = old_prod_env.decode('utf-8')
    #old_prod_env = str(argv[1])
    old_db = datum.connect(config['DATABASES'][new_db_map[old_prod_env]])
    new_db = datum.connect(config['DATABASES']['engine'])
#    old_db = datum.connect(config['DATABASES']['engine_staging'])
    unused_tables =  ('spatial_ref_sys', 'alembic_version', 'multiple_seg_line', 'service_area_diff', 'address_zip', 'zip_range')
    changed_tables = ('address_error',)
    ignore_tables = unused_tables + changed_tables

    return {'new_db': new_db, 'old_db': old_db, 'unused_tables': unused_tables, 'changed_tables': changed_tables, 'ignore_tables': ignore_tables}

def test_no_duplicates(startup):
    """ Don't allow duplicate street_addresses in address_summary """

    new_db = startup['new_db']
    total_stmt = "select count(*) as total_addresses from address_summary"
    distinct_stmt = "select count(*) as distinct_addresses from (select distinct street_address from address_summary) foo"
    num_total_row = new_db.execute(total_stmt)
    num_distinct_row = new_db.execute(distinct_stmt)
    num_total = num_total_row[0]['total_addresses']
    num_distinct = num_distinct_row[0]['distinct_addresses']
    assert num_total == num_distinct


def test_compare_num_tables(startup):
    """Test #1: Check if all tables are included in build"""
    # assert len(startup['new_db'].tables) == len(startup['old_db'].tables)
    new_db = startup['new_db']
    old_db = startup['old_db']
    table_count_stmt = "select count(*) from information_schema.tables where table_schema = 'public' AND table_type = 'BASE TABLE'"
    new_table_count = new_db.execute(table_count_stmt)
    old_table_count = old_db.execute(table_count_stmt)
    assert new_table_count == old_table_count

def test_num_rows_bt_db_tables(startup):
    """"Test #2: Check if all tables within 10% of rows as old version"""
    new_db = startup['new_db']
    old_db = startup['old_db']
    list_tables_stmt = "select table_name from information_schema.tables where table_schema = 'public' AND table_type = 'BASE TABLE'"
    new_db_tables = new_db.execute(list_tables_stmt)
    old_db_tables = old_db.execute(list_tables_stmt)
    # new_db_tables = startup['new_db'].tables
    for ntable in new_db_tables:
        table_name = ntable['table_name']

        if table_name in startup['ignore_tables']:
            continue

        # ndb_table = startup['new_db'][ntable]
        # n_rows = ndb_table.count
        row_count_stmt = "select count(*) as count from {}".format(table_name)
        n_rows = new_db.execute(row_count_stmt)
        o_rows = old_db.execute(row_count_stmt)
        # odb_table = startup['old_db'][ntable]
        # o_rows = odb_table.count
        fdif = abs((n_rows[0]['count'] - o_rows[0]['count']) / o_rows[0]['count'])

        assert fdif <= 0.1, (ntable, fdif)


def test_geocode_types(startup):
    """Test #3: Check if all geocode types present (compare new an old builds)"""
    new_db = startup['new_db']
    old_db = startup['old_db']

    def get_geo_types(db):
        stmt = "SELECT DISTINCT geocode_type FROM geocode"
        geo_types = db.execute(stmt)
        results = sorted([f['geocode_type'] for f in geo_types])

        return results

    n_geo_types = get_geo_types(new_db)
    o_geo_types = get_geo_types(old_db)

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
    new_db_result = startup['new_db'].execute(stmt)
    old_db_result = startup['old_db'].execute(stmt)

    unmatched_indexes = []
    for old_row in old_db_result:
        #assert 1 == 2, (old_row, dir(old_row), old_row.items())
        found = False
        if found: continue
        for new_row in new_db_result:
            if new_row['Name'] == old_row['Name']:
                found = True
                break
        if not found:
            unmatched_indexes.append({'name': old_row['Name'], 'table': old_row['Table']})
    assert len(unmatched_indexes) == 0, (unmatched_indexes)
    # assert len(new_db_result) == len(old_db_result), (
    # "new db has {} more indexes.".format(len(new_db_result) - len(old_db_result)))


@pytest.fixture(scope="module")
def teardown():
    """Teardown fixture: close db connections"""
    new_db = startup['new_db']
    old_db = startup['old_db']
    yield
    new_db.close()
    old_db.close()
    return (new_db, old_db)


