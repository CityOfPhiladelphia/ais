import subprocess
from collections import OrderedDict
from functools import partial
import petl as etl
import geopetl
import cx_Oracle
import psycopg2
from shapely.wkt import loads
from shapely.ops import transform
import pyproj
from ais import app
from ais.util import parse_url


###################################
# This script generates reports and writes them to tables in Databridge
# address_summary, service_area_summary and true_range
# They are for integrating standardized addresses with department records.
# Department records meaning dor parcel_id, pwd parcel_id, OPA account number, eclipes location id
# These departments will import these tables for their own usage.
#
# address_summary: contains standardized address components + primary keys and authoritative data
# service_area_summary: for each address, has ids for each service area the point is located in
# true_range: Interpolated address location along the street segment



config = app.config
read_db_string = config['DATABASES']['engine']
#write_db_string = config['DATABASES']['gis_ais']
write_db_string = config['DATABASES']['gis_ais_test']
parsed_read_db_string = parse_url(read_db_string)
parsed_write_db_string = parse_url(write_db_string)

address_summary_write_table_name = 'ADDRESS_SUMMARY'
service_area_summary_write_table_name = 'SERVICE_AREA_SUMMARY'
dor_condo_error_table_name = 'DOR_CONDOMINIUM_ERROR'
true_range_write_table_name = 'TRUE_RANGE'
address_error_write_table_name = 'AIS_ADDRESS_ERROR'


read_pass = parsed_read_db_string['password']
read_user = parsed_read_db_string['user']
read_host = parsed_read_db_string['host']
read_db = parsed_read_db_string['db_name']
read_dsn = f"dbname={read_db} host={read_host} user={read_user} password={read_pass}"
read_conn = psycopg2.connect(read_dsn)

def database_connect(dsn):
    # Connect to database
    db_connect = cx_Oracle.connect(dsn)
    print('Connected to %s' % db_connect)
    cursor = db_connect.cursor()
    return cursor

write_user = parsed_write_db_string['user']
write_pw = parsed_write_db_string['password']
write_host = parsed_write_db_string['host']
write_dsn = f'{write_user}/{write_pw}@{write_host}'
print('DEBUG: ' + write_dsn)
oracle_cursor = database_connect(write_dsn)


print(f'\nReading from local DB: {read_dsn}')
print(f'Writing to: {write_dsn}\n'.replace(write_pw, 'CENSORED'))
#########################################################################################################################
## UTILS
#########################################################################################################################
def make_address_full(comps):
    address_low = comps['address_low']
    address_low_suffix = comps['address_low_suffix']
    address_low_frac = comps['address_low_frac']
    address_high = comps['address_high']

    address_full = str(address_low)
    address_full += address_low_suffix if address_low_suffix else ''
    address_full += ' ' + address_low_frac if address_low_frac else ''

    if address_high:
        address_high = str(address_high)
        if len(address_high) < 2:
            address_high = '0' + address_high
        address_full += '-' + address_high[-2:]

    return address_full


def transform_coords(comps):
    x_coord = comps['geocode_x']
    y_coord = comps['geocode_y']

    if x_coord is None or y_coord is None:
        return [None, None]

    point = loads('POINT({x} {y})'.format(x=x_coord, y=y_coord))

    project = partial(
        pyproj.transform,
        pyproj.Proj(init='EPSG:2272', preserve_units=True),
        pyproj.Proj(init='EPSG:4326', preserve_units=True))

    transformed_point = transform(project, point)
    x = transformed_point.x
    y = transformed_point.y

    return [x, y]

address_summary_mapping = {
    'id': 'id',
    'address': 'address_low',
    'address_suffix': 'address_low_suffix',
    'address_fractional': 'address_low_frac',
    'address_high': 'address_high',
    'address_full': 'address_full',
    'street_predir': 'street_predir',
    'street_name': 'street_name',
    'street_suffix': 'street_suffix',
    'street_postdir': 'street_postdir',
    'unit_type': 'unit_type',
    'unit_num': 'unit_num',
    'zip_code': 'zip_code',
    'zip_4': 'zip_4',
    'street_address': 'street_address',
    'opa_account_num': 'opa_account_num',
    'opa_owners': 'opa_owners',
    'opa_address': 'opa_address',
    'info_companies': 'info_companies',
    'info_residents': 'info_residents',
    'voters': 'voters',
    'pwd_account_nums': 'pwd_account_nums',
    'li_address_key': 'li_address_key',
    'seg_id': 'seg_id',
    'seg_side': 'seg_side',
    'dor_parcel_id': 'dor_parcel_id',
    'pwd_parcel_id': 'pwd_parcel_id',
    'geocode_type': 'geocode_type',
    'geocode_x': 'geocode_x',
    'geocode_y': 'geocode_y',
    'geocode_lat': 'geocode_lat',
    'geocode_lon': 'geocode_lon',
    'eclipse_location_id': 'eclipse_location_id',
    'zoning_document_ids': 'zoning_document_ids',
    'bin': 'bin',
    'li_parcel_id': 'li_parcel_id',
    'street_code': 'street_code',
    'shape': 'shape'
}


def standardize_nulls(val):
    if type(val) == str:
        return None if val.strip() == '' else val
    else:
        return None if val == 0 else val


def concatenate_dor_address(source_comps):
    # Get attributes
    address_low = source_comps[field_map['address_low']]
    address_low_suffix = source_comps[field_map['address_low_suffix']]
    address_high = source_comps[field_map['address_high']]
    street_predir = source_comps[field_map['street_predir']]
    street_name = source_comps[field_map['street_name']]
    street_suffix = source_comps[field_map['street_suffix']]
    street_postdir = source_comps[field_map['street_postdir']]
    unit_num = source_comps[field_map['unit_num']]
    source_address = None
    street_full = ''
    # Make street full
    if street_name:
        street_comps = [street_predir, street_name, street_suffix, \
                        street_postdir]
        street_full = ' '.join([x for x in street_comps if x])

    # Only accept numeric address_low_suffixes = 2 for transformation to 1/2; discard other numeric suffixes
    address_low_fractional = None
    try:
        address_low_suffix_int = int(address_low_suffix)
        if address_low_suffix_int == 2:
            address_low_fractional = '1/2'
        address_low_suffix = None
    except:
        pass

    address_full = None
    if address_low:
        address_full = str(address_low)
        if address_low_suffix:
            address_full += address_low_suffix
        if address_low_fractional:
            address_full += ' ' + address_low_fractional
        if address_high:
            address_full += '-' + str(address_high)

    # Get unit
    unit_full = None
    if standardize_nulls(unit_num):
        unit_full = '# {}'.format(unit_num)

    if address_full and street_full:
        source_address_comps = [address_full, street_full, unit_full]
        source_address = ' '.join([x for x in source_address_comps if x])

    return source_address if source_address != None else ''
#############################################
# Read in files, format and write to tables #
#############################################
#################
# ADDRESS ERROR #
#################
print("Writing address_error table...")
etl.fromdb(read_conn, 'select * from address_error').rename('level', 'error_or_warning').tooraclesde(write_dsn, address_error_write_table_name)
##############
# TRUE RANGE #
##############
print(f"\nWriting {true_range_write_table_name} table...")
#etl.fromdb(read_conn, 'select * from true_range').tooraclesde(write_dsn, true_range_write_table_name)
rows = etl.fromdb(read_conn, 'select * from true_range')
rows.tooraclesde(write_dsn, true_range_write_table_name)


########################
# SERVICE AREA SUMMARY #
########################
print(f"\nWriting {service_area_summary_write_table_name} table...")
service_area_rows = etl.fromdb(read_conn, 'select * from service_area_summary')
service_area_rows = etl.rename(service_area_rows, {'neighborhood_advisory_committee': 'neighborhood_advisory_committe'}, )
service_area_rows.tooraclesde(write_dsn, service_area_summary_write_table_name)


########################
# ADDRESS SUMMARY #
########################
print("\nCreating transformed ADDRESS_SUMMARY table...")
# add address_full and transformed coords, as well as shape as WKT, and only export rows that have been geocoded:
print('Grabbing fields from local database..')
addr_summary_rows = etl.fromdb(read_conn, '''
                select *, 
                st_x(st_transform(st_setsrid(st_point(geocode_x, geocode_y), 2272), 4326)) as geocode_lon,
                st_y(st_transform(st_setsrid(st_point(geocode_x, geocode_y), 2272), 4326)) as geocode_lat,
                public.ST_AsText(st_point(geocode_x, geocode_y)) as shape
                from address_summary;
                ''')

print('Synthesizing "ADDRESS_FULL" column..')
addr_summary_rows = etl.addfield(addr_summary_rows, 'address_full', (lambda a: make_address_full(
    {'address_low': a['address_low'], 'address_low_suffix': a['address_low_suffix'],
     'address_low_frac': a['address_low_frac'], 'address_high': a['address_high']})))
    
# Remove rows with null coordinates
addr_summary_rows = etl.select(addr_summary_rows, lambda s: s.geocode_x is not None)

# Rename field based on this dictionary
# Note that its reversed to what you'd expect, values are the original field names
# and the keys are what the fields are renamed to.
addr_summary_rows = etl.fieldmap(addr_summary_rows, address_summary_mapping)

# Cut out fields that aren't in our map to match it up with Oracle
keep_fields = list(address_summary_mapping.keys())
addr_summary_rows = etl.cut(addr_summary_rows, *keep_fields)

temp_as_table_name = 'T_ADDRESS_SUMMARY'
prod_as_table_name = 'ADDRESS_SUMMARY'

try:
    create_stmt = f'CREATE TABLE {temp_as_table_name} AS (SELECT * FROM {prod_as_table_name} WHERE 1=0)'
    print(f'Creating Oracle table with statement: {create_stmt}')
    oracle_cursor.execute(create_stmt)
    oracle_cursor.execute('COMMIT')
except Exception as e:
    if 'ORA-00955' not in str(e):
        raise e
    else:
        print(f'Table {temp_as_table_name} already exists.')

# Assert our fields match between our devised petl object and the destination oracle table.
field_stmt = "SELECT column_name FROM all_tab_cols WHERE table_name = 'T_ADDRESS_SUMMARY' AND owner = 'GIS_AIS'  AND column_name NOT LIKE 'SYS_%'"
oracle_cursor.execute(field_stmt)
oracle_fields = oracle_cursor.fetchall()
oracle_fields = [x[0].lower() for x in oracle_fields]
oracle_fields.remove('objectid')

# Validate that we have the expected headers in our petl object
addr_summary_rows.validate(header=tuple(oracle_fields))

print('Writing to csv file..')
addr_summary_rows.tocsv("address_summary_transformed.csv", write_header=True)

print('Writing to temp table "T_ADDRESS_SUMMARY"..')
addr_summary_rows.tooraclesde(dbo=write_dsn, table_name='T_ADDRESS_SUMMARY', srid=2272)

grant_sql1 = "GRANT SELECT on {} to SDE".format(temp_as_table_name)
grant_sql2 = "GRANT SELECT ON {} to GIS_SDE_VIEWER".format(temp_as_table_name)
grant_sql3 = "GRANT SELECT ON {} to GIS_AIS_SOURCES".format(temp_as_table_name)


# Swap prod/temp tables:
# Oracle does not allow table modification within a transaction, so make individual transactions:

# First make the temp table and setup permissions
print('Renaming temp table to prod table to minimize downtime..')
oracle_cursor.execute(grant_sql1)
oracle_cursor.execute(grant_sql2)
oracle_cursor.execute(grant_sql3)

sql1 = 'ALTER TABLE {} RENAME TO {}_old'.format(prod_as_table_name, prod_as_table_name)
sql2 = 'ALTER TABLE {} RENAME TO {}'.format(temp_as_table_name, prod_as_table_name)
sql3 = 'DROP TABLE {}_old'.format(prod_as_table_name)


try:
    oracle_cursor.execute(sql1)
except:
    print("Could not rename {} table. Does it exist?".format(temp_as_table_name))
    raise
try:
    oracle_cursor.execute(sql2)
except:
    print("Could not rename {} table. Does it exist?".format(prod_as_table_name))
    rb_sql = 'ALTER TABLE {}_old RENAME TO {}'.format(prod_as_table_name, prod_as_table_name)
    oracle_cursor.execute(rb_sql)
    raise
try:
    oracle_cursor.execute(sql3)
except:
    print("Could not drop {}_old table. Do you have permission?".format(prod_as_table_name))
    rb_sql1 = 'DROP TABLE {}'.format(temp_as_table_name)
    oracle_cursor.execute(rb_sql1)
    rb_sql2 = 'ALTER TABLE {}_old RENAME TO {}'.format(prod_as_table_name, prod_as_table_name)
    oracle_cursor.execute(rb_sql2)
    raise

#########################
# DOR CONDOMINIUM ERROR #
#########################
print(f"\nWriting to DOR_CONDOMINIUM_ERROR table...")
dor_condominium_error_table = etl.fromdb(read_conn, 'select * from dor_condominium_error')
dor_condominium_error_table = etl.rename(dor_condominium_error_table, {'parcel_id': 'mapref', 'unit_num': 'condounit',})
dor_condominium_error_table.tooraclesde(write_dsn, dor_condo_error_table_name)

read_conn.close()
