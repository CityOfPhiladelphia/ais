from datum import Database
import pytest
import instance.config as config

@pytest.fixture
def startup():
    """Startup fixture: make database connections and define tables to ignore"""
    new_db = Database(config.DATABASES['engine_production'])
    old_db = Database(config.DATABASES['engine_staging'])

    #system tables
    ignore_tables = ('spatial_ref_sys', 'alembic_version', 'multiple_seg_line', 'service_area_diff')

    #tables of question id'd in debugging
    #mysterious_tables = ('address_link', 'parcel_curb')
    #ignore_tables = ignore_tables + mysterious_tables

    return {'new_db':new_db, 'old_db':old_db, 'ignore_tables':ignore_tables}


def test_compare_num_tables(startup):
    """Test #1: Check if all tables are included in build"""
    assert len(startup['new_db'].tables) == len(startup['old_db'].tables)


def test_num_rows_bt_db_tables(startup):
    """"Test #2: Check if all tables within 10% of rows as old version"""
    new_db_tables = startup['new_db'].tables
    for ntable in new_db_tables:

        if ntable in startup['ignore_tables']:
            continue

        ndbtable = startup['new_db'][ntable]
        n_rows = ndbtable.count
        odbtable = startup['old_db'][ntable]
        o_rows = odbtable.count
        fdif = abs((n_rows - o_rows) / o_rows)

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

@pytest.fixture(scope="module")
def teardown():
    """Teardown fixture: close db connections"""
    new_db = startup['new_db']
    old_db = startup['old_db']
    yield
    new_db.close()
    old_db.close()
    return (new_db, old_db)


