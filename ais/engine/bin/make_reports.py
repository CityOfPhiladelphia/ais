import subprocess
from collections import OrderedDict
from functools import partial
import petl as etl
import cx_Oracle
import psycopg2
import geopetl
from shapely.wkt import loads
from shapely.ops import transform
import pyproj
from ais import app
from ais.util import parse_url

config = app.config
read_db_string = config['DATABASES']['engine']
write_db_string = config['DATABASES']['gis_ais']
parsed_read_db_string = parse_url(read_db_string)
parsed_write_db_string = parse_url(write_db_string)
write_dsn = parsed_write_db_string['user'] + '/' + parsed_write_db_string['password'] + '@' + parsed_write_db_string[
    'host']
address_summary_write_table_name = 'ADDRESS_SUMMARY'
service_area_summary_write_table_name = 'SERVICE_AREA_SUMMARY'
dor_condo_error_table_name = 'DOR_CONDOMINIUM_ERROR'
true_range_write_table_name = 'TRUE_RANGE'
address_error_write_table_name = 'AIS_ADDRESS_ERROR'
source_address_write_table_name = 'SOURCE_ADDRESS'
read_conn = psycopg2.connect(
    "dbname={db_name} user={user}".format(db_name=parsed_read_db_string['db_name'], user=parsed_read_db_string['user']))
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


mapping = OrderedDict([
    ('id', 'id'),
    ('address', 'address_low'),
    ('address_suffix', 'address_low_suffix'),
    ('address_fractional', 'address_low_frac'),
    ('address_high', 'address_high'),
    ('address_full', 'address_full'),
    ('street_predir', 'street_predir'),
    ('street_name', 'street_name'),
    ('street_suffix', 'street_suffix'),
    ('street_postdir', 'street_postdir'),
    ('unit_type', 'unit_type'),
    ('unit_num', 'unit_num'),
    ('zip_code', 'zip_code'),
    ('zip_4', 'zip_4'),
    ('street_address', 'street_address'),
    ('opa_account_num', 'opa_account_num'),
    ('opa_owners', 'opa_owners'),
    ('opa_address', 'opa_address'),
    ('info_companies', 'info_companies'),
    ('info_residents', 'info_residents'),
    ('voters', 'voters'),
    ('pwd_account_nums', 'pwd_account_nums'),
    ('li_address_key', 'li_address_key'),
    ('seg_id', 'seg_id'),
    ('seg_side', 'seg_side'),
    ('dor_parcel_id', 'dor_parcel_id'),
    ('pwd_parcel_id', 'pwd_parcel_id'),
    ('geocode_type', 'geocode_type'),
    ('geocode_x', 'geocode_x'),
    ('geocode_y', 'geocode_y'),
    ('geocode_lat', 'geocode_lat'),
    ('geocode_lon', 'geocode_lon'),
    ('eclipse_location_id', 'eclipse_location_id'),
    ('zoning_document_ids', 'zoning_document_ids'),
    ('bin', 'bin'),
    ('li_parcel_id', 'li_parcel_id'),
    ('street_code', 'street_code')
])


def standardize_nulls(val):
    if type(val) == str:
        return None if val.strip() == '' else val
    else:
        return None if val == 0 else val

#############################################
# Read in files, format and write to tables #
#############################################
#################
# ADDRESS ERROR #
#################
print("Writing address_error table...")
etl.fromdb(read_conn, 'select * from address_error').rename('level', 'error_or_warning').tooraclesde(write_dsn, address_error_write_table_name)
##################
# SOURCE ADDRESS #
##################
print("Writing source_address table...")
etl.fromdb(read_conn, 'select * from source_address').tooraclesde(write_dsn, source_address_write_table_name)
##############
# TRUE RANGE #
##############
print("Writing true_range table...")
etl.fromdb(read_conn, 'select * from true_range').tooraclesde(write_dsn, true_range_write_table_name)
########################
# SERVICE AREA SUMMARY #
########################
print("Writing service_area_summary table...")
etl.fromdb(read_conn, 'select * from service_area_summary')\
  .rename({'neighborhood_advisory_committee': 'neighborhood_advisory_committe'}, )\
  .tooraclesde(write_dsn, service_area_summary_write_table_name)
########################
# ADDRESS SUMMARY #
########################
print("Creating transformed address_summary table...")
# only export rows that have been geocoded:
address_summary_out_table = etl.fromdb(read_conn, 'select * from address_summary') \
    .addfield('address_full', (lambda a: make_address_full(
    {'address_low': a['address_low'], 'address_low_suffix': a['address_low_suffix'],
     'address_low_frac': a['address_low_frac'], 'address_high': a['address_high']}))) \
    .addfield('temp_lonlat', (lambda a: transform_coords({'geocode_x': a['geocode_x'], 'geocode_y': a['geocode_y']}))) \
    .addfield('geocode_lon', lambda a: a['temp_lonlat'][0]) \
    .addfield('geocode_lat', lambda a: a['temp_lonlat'][1]) \
    .cutout('temp_lonlat') \
    .select(lambda s: s.geocode_x is not None) \
    .fieldmap(mapping) 

address_summary_out_table.todb(read_conn, "address_summary_transformed", create=True, sample=0)
address_summary_out_table.tocsv("address_summary_transformed.csv", write_header=True)
#########################
# DOR CONDOMINIUM ERROR #
#########################
print("Writing dor_condominium_error table...")
dor_condominium_error_table = etl.fromdb(read_conn, 'select * from dor_condominium_error') \
    .rename({'parcel_id': 'mapref', 'unit_num': 'condounit',}) \
    .tooraclesde(write_dsn, dor_condo_error_table_name)

print("Cleaning up...")
read_conn.close()
