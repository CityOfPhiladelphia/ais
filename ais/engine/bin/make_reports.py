import subprocess
from collections import OrderedDict
from functools import partial
import petl as etl
import geopetl
import psycopg2
import re
from ais import app
from ais.util import parse_url


###################################
# This script generates reports and writes them to tables in Databridge
# address_summary, service_area_summary and true_range
# They are for integrating standardized addresses with department records.
# Department records meaning dor parcel_id, pwd parcel_id, OPA account number, Eclipse location id
# These departments will import these tables for their own usage.
#
# address_summary: contains standardized address components + primary keys and authoritative data
# service_area_summary: for each address, has ids for each service area the point is located in
# true_range: Interpolated address location along the street segment


config = app.config
read_db_string = config['DATABASES']['engine']
write_db_string = config['DATABASES']['citygeo']
parsed_read_db_string = parse_url(read_db_string)
parsed_write_db_string = parse_url(write_db_string)

ADDRESS_SUMMARY_WRITE_TABLE_NAME = 'citygeo.address_summary'
SERVICE_AREA_SUMMARY_WRITE_TABLE_NAME = 'citygeo.service_area_summary'
DOR_CONDO_ERROR_TABLE_NAME = 'citygeo.dor_condominium_error'
TRUE_RANGE_WRITE_TABLE_NAME = 'citygeo.true_range'
ADDRESS_ERROR_WRITE_TABLE_NAME = 'citygeo.ais_address_error'
SOURCE_ADDRESS_WRITE_TABLE_NAME = 'citygeo.source_address'


read_pass = parsed_read_db_string['password']
read_user = parsed_read_db_string['user']
read_host = parsed_read_db_string['host']
read_db = parsed_read_db_string['db_name']
read_dsn = f"dbname={read_db} host={read_host} user={read_user} password={read_pass}"
read_conn = psycopg2.connect(read_dsn)


write_dsn = write_db_string.split('//')[1].replace(':','/')
conn_components = re.split(r'\/|@', write_dsn)
write_user, write_pw, write_host, _, write_hostname = conn_components
write_conn = psycopg2.connect(f'user={write_user} password={write_pw} host={write_host} dbname={write_hostname}')

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


def upload_csv_to_postgres(csv_file_path, table_name, conn):
    """
    Upload a CSV file to a PostgreSQL table using the copy_expert method.
    
    Parameters:
    - csv_file_path: Path to the CSV file.
    - table_name: Name of the target table in PostgreSQL.
    - conn: active connection to the PostgreSQL database.
    """
    try:
        # Establish connection to PostgreSQL
        cursor = conn.cursor()
        header = etl.fromcsv(csv_file_path)[0]
        fields = ', '.join(header)
        header = None

        # Begin a transaction block
        conn.autocommit = False

        # Step 1: Delete all existing rows in the table
        cursor.execute(f"DELETE FROM {table_name}")
        print(f"Deleted all rows from {table_name}.")

        # Step 2: Open the CSV file and insert the new data
        with open(csv_file_path, 'r') as f:
            # Use copy_expert to upload the CSV data
            sql_copy = f"""
                COPY {table_name} ({fields}) FROM STDIN WITH CSV HEADER DELIMITER ','
                """
            print(sql_copy)
            cursor.copy_expert(sql_copy, f)

        # Step 3: Commit the transaction if all operations succeed
        conn.commit()
        print(f"Data from {csv_file_path} uploaded successfully to {table_name}.")

    except (Exception, psycopg2.DatabaseError) as error:
        # If an error occurs, roll back the entire transaction
        if conn:
            conn.rollback()
        print(f"Error: {error}. Transaction rolled back.")
        # Commit the transaction
        conn.commit()
        raise error
    
    finally:
        if cursor:
            cursor.close()

#############################################
# Read in files, format and write to tables #
#############################################
#################
# ADDRESS ERROR #
#################
print(f"Writing address_error table to {ADDRESS_ERROR_WRITE_TABLE_NAME}...")
etl.fromdb(read_conn, 'select * from address_error').rename('level', 'error_or_warning').topostgis(write_conn, ADDRESS_ERROR_WRITE_TABLE_NAME)
##################
# SOURCE ADDRESS #
##################
print(f"Writing source_address table to {SOURCE_ADDRESS_WRITE_TABLE_NAME}...")
etl.fromdb(read_conn, 'select * from source_address').topostgis(write_conn, SOURCE_ADDRESS_WRITE_TABLE_NAME)
##############
# TRUE RANGE #
##############
print(f"\nWriting true_range table to {TRUE_RANGE_WRITE_TABLE_NAME}...")
true_range_rows = etl.fromdb(read_conn, 'select * from true_range')
true_range_rows.topostgis(write_conn, TRUE_RANGE_WRITE_TABLE_NAME)


########################
# SERVICE AREA SUMMARY #
########################
print(f"\nWriting service_area_summary table to {SERVICE_AREA_SUMMARY_WRITE_TABLE_NAME}...")
service_area_rows = etl.fromdb(read_conn, 'select * from service_area_summary')
service_area_rows = etl.rename(service_area_rows, {'neighborhood_advisory_committee': 'neighborhood_advisory_committe'}, )
if 'objectid' in etl.header(service_area_rows):
    service_area_rows = etl.cutout(service_area_rows, 'objectid')
service_area_rows.topostgis(write_conn, SERVICE_AREA_SUMMARY_WRITE_TABLE_NAME)


########################
# ADDRESS SUMMARY #
########################
print("\nCreating transformed address_summary table...")
# add address_full and transformed coords, as well as shape as WKT, and only export rows that have been geocoded:
print('Grabbing fields from local database..')
addr_summary_rows = etl.fromdb(read_conn, '''
                select *, 
                st_x(st_transform(st_setsrid(st_point(geocode_x, geocode_y), 2272), 4326)) as geocode_lon,
                st_y(st_transform(st_setsrid(st_point(geocode_x, geocode_y), 2272), 4326)) as geocode_lat,
                public.ST_AsEWKT(st_setsrid(st_point(geocode_x, geocode_y), 2272)) as shape
                from address_summary;
                ''') # need to use AsEWKT and enforce srid explicitly for copy_expert to work from the csv

print('Synthesizing "address_full" column..')
addr_summary_rows = etl.addfield(addr_summary_rows, 'address_full', (lambda a: make_address_full(
    {'address_low': a['address_low'], 'address_low_suffix': a['address_low_suffix'],
     'address_low_frac': a['address_low_frac'], 'address_high': a['address_high']})))
    
# Remove rows with null coordinates
addr_summary_rows = etl.select(addr_summary_rows, lambda s: s.geocode_x is not None)

# Rename field based on this dictionary
# Note that its reversed to what you'd expect, values are the original field names
# and the keys are what the fields are renamed to.
addr_summary_rows = etl.fieldmap(addr_summary_rows, address_summary_mapping)

# Cut out fields that aren't in our map to match it up with database
keep_fields = list(address_summary_mapping.keys())
addr_summary_rows = etl.cut(addr_summary_rows, *keep_fields)

print('Writing to csv file..')
ADDRESS_SUMMARY_CSV_FILENAME = "address_summary_transformed.csv"
addr_summary_rows.tocsv(ADDRESS_SUMMARY_CSV_FILENAME, write_header=True)

print(f'Writing to table {ADDRESS_SUMMARY_WRITE_TABLE_NAME}...')
#addr_summary_rows.topostgis(write_conn, ADDRESS_SUMMARY_WRITE_TABLE_NAME, from_srid=2272)
upload_csv_to_postgres(ADDRESS_SUMMARY_CSV_FILENAME, ADDRESS_SUMMARY_WRITE_TABLE_NAME, write_conn)

#########################
# DOR CONDOMINIUM ERROR #
#########################
print(f"\nWriting dor_condominum_error to {DOR_CONDO_ERROR_TABLE_NAME} table...")
dor_condominium_error_rows = etl.fromdb(read_conn, 'select * from dor_condominium_error')
dor_condominium_error_rows = etl.rename(dor_condominium_error_rows, {'parcel_id': 'mapref', 'unit_num': 'condounit',})
if 'objectid' in etl.header(dor_condominium_error_rows):
    dor_condominium_error_rows = etl.cutout(dor_condominium_error_rows, 'objectid')
dor_condominium_error_rows.topostgis(write_conn, DOR_CONDO_ERROR_TABLE_NAME)

read_conn.close()

print("All writings complete!")
