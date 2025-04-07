import petl as etl
import psycopg2
from datetime import datetime
from ais import app
import re

def main():
    start = datetime.now()
    print('Starting...')

    """SET UP"""
    DEV = False
    config = app.config
    engine_dsn = config['DATABASES']['engine']
    db_user = engine_dsn[engine_dsn.index("//") + 2:engine_dsn.index(":", engine_dsn.index("//"))]
    db_pw = engine_dsn[engine_dsn.index(":",engine_dsn.index(db_user)) + 1:engine_dsn.index("@")]
    db_name = engine_dsn[engine_dsn.index("/", engine_dsn.index("@")) + 1:]
    pg_db = psycopg2.connect('dbname={db_name} user={db_user} password={db_pw} host=localhost'.format(db_name=db_name, db_user=db_user, db_pw=db_pw))

    # get source table params
    source_def = config['BASE_DATA_SOURCES']['condos']['dor']
    source_db_name = source_def['db']
    source_db_url = config['DATABASES'][source_db_name]
    dsn = source_db_url.split('//')[1].replace(':','/')
    conn_components = re.split(r'\/|@', dsn)
    source_user = conn_components[0]
    source_pw = conn_components[1]
    source_host = conn_components[2]
    # source_port = conn_components[3]
    # source_hostname = conn_components[4]
    source_conn = psycopg2.connect(f'user={source_user} password={source_pw} host={source_host} dbname={source_db_name}')
    source_table_name = source_def['table']
    source_field_map = source_def['field_map']

    # Read DOR CONDO rows from source
    print("Reading condos...")
    # TODO: get fieldnames from source_field_map
    dor_condo_read_stmt = '''
        select condounit, objectid, mapref from {dor_condo_table}
        where status in (1,3)
    '''.format(dor_condo_table = source_table_name)
    source_dor_condo_rows = etl.fromdb(source_conn, dor_condo_read_stmt).fieldmap(source_field_map)
    if DEV:
        print(etl.look(source_dor_condo_rows))

    # Read DOR Parcel rows from engine db
    print("Reading parcels...")
    dor_parcel_read_stmt = '''
        select parcel_id, street_address, address_low, address_low_suffix, address_low_frac, address_high, street_predir, 
        street_name, street_suffix, street_postdir, street_full from {dor_parcel_table}
        '''.format(dor_parcel_table='dor_parcel')
    engine_dor_parcel_rows = etl.fromdb(pg_db, dor_parcel_read_stmt)
    if DEV:
        print(etl.look(engine_dor_parcel_rows))

    # Get duplicate parcel_ids:
    non_unique_parcel_id_rows = engine_dor_parcel_rows.duplicates(key='parcel_id')
    unique_parcel_id_rows = etl.complement(engine_dor_parcel_rows, non_unique_parcel_id_rows)

    # Get address comps for condos by joining to dor_parcel with unique parcel_id on parcel_id:
    print("Relating condos to parcels...")
    joined = etl.join(source_dor_condo_rows, unique_parcel_id_rows, key='parcel_id') \
        .convert('street_address', lambda a, row: row.street_address + ' # ' + row.unit_num, pass_row=True)
    print("joined rowcount: ", etl.nrows(joined))
    if DEV:
        print(etl.look(joined))

    # Calculate errors
    print("Calculating errors...")
    unjoined = etl.antijoin(source_dor_condo_rows, joined, key='source_object_id')
    print("unjoined rowcount: ", etl.nrows(unjoined))
    dor_condos_unjoined_unmatched = etl.antijoin(unjoined, non_unique_parcel_id_rows, key='parcel_id').addfield('reason', 'non-active/remainder mapreg')
    print("non-active/remainder mapreg error rowcount: ", etl.nrows(dor_condos_unjoined_unmatched))
    if DEV:
        print(etl.look(dor_condos_unjoined_unmatched))
    dor_condos_unjoined_duplicates = etl.antijoin(unjoined, dor_condos_unjoined_unmatched, key='source_object_id').addfield('reason', 'non-unique active/remainder mapreg')
    print("non-unique active/remainder mapreg error rowcount: ", etl.nrows(dor_condos_unjoined_duplicates))
    if DEV:
        print(etl.look(dor_condos_unjoined_duplicates))
    error_table = etl.cat(dor_condos_unjoined_unmatched, dor_condos_unjoined_duplicates)
    if DEV:
        print(etl.look(error_table))

    # Write to engine db
    if not DEV:
        print('Writing condos...')
        joined.todb(pg_db, 'dor_condominium')
        print('Writing errors...')
        error_table.todb(pg_db, 'dor_condominium_error')

    print("Completed in ", datetime.now() - start, " minutes.")
