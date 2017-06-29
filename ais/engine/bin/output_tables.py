from collections import OrderedDict
from functools import partial
import petl as etl
from datetime import datetime
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
write_dsn = parsed_write_db_string['user'] + '/' + parsed_write_db_string['password'] + '@' + parsed_write_db_string['host']
address_summary_write_table_name = 'ADDRESS_SUMMARY'
service_area_summary_write_table_name = 'SERVICE_AREA_SUMMARY'
true_range_write_table_name = 'TRUE_RANGE'
read_conn = psycopg2.connect("dbname={db_name} user={user}".format(db_name=parsed_read_db_string['db_name'], user=parsed_read_db_string['user']))
datetimenow = datetime.now()
print(datetimenow)
#########################################################################################################################
## Read in files, format and write to tables
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
    point = loads('POINT({x} {y})'.format(x=x_coord, y=y_coord))
    shape = point.wkt

    project = partial(
        pyproj.transform,
        pyproj.Proj(init='EPSG:2272', preserve_units=True),
        pyproj.Proj(init='EPSG:4326', preserve_units=True))

    transformed_point = transform(project, point)
    x = transformed_point.x
    y = transformed_point.y

    return [x,y, shape]

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
    ('shape', 'shape'),
    ('eclipse_location_id', 'eclipse_location_id'),
    ('zoning_document_ids', 'zoning_document_ids')
    ])

########################
# TRUE RANGE #
########################
true_range_in_table = etl.fromdb(read_conn, 'select * from true_range')
# print(etl.look(true_range_in_table))
etl.tooraclesde(true_range_in_table, write_dsn, true_range_write_table_name)
########################
# SERVICE AREA SUMMARY #
########################
service_area_summary_in_table = etl.fromdb(read_conn, 'select * from service_area_summary')
# print(etl.look(service_area_summary_in_table))
etl.tooraclesde(service_area_summary_in_table, write_dsn, service_area_summary_write_table_name)
########################
# ADDRESS AREA SUMMARY #
########################
address_summary_in_table = etl.fromdb(read_conn, 'select * from address_summary')
address_summary_out_table = address_summary_in_table \
    .addfield('address_full', (lambda a: make_address_full({'address_low': a['address_low'], 'address_low_suffix': a['address_low_suffix'], 'address_low_frac': a['address_low_frac'], 'address_high': a['address_high']}))) \
    .addfield('temp_lonlat', (lambda a: transform_coords({'geocode_x': a['geocode_x'], 'geocode_y': a['geocode_y']}))) \
    .addfield('geocode_lon', lambda a: a['temp_lonlat'][0]) \
    .addfield('geocode_lat', lambda a: a['temp_lonlat'][1]) \
    .addfield('shape', lambda a: a['temp_lonlat'][2]) \
    .cutout('temp_lonlat') \
    .fieldmap(mapping)

# print(etl.look(address_summary_out_table))
etl.tooraclesde(address_summary_out_table, write_dsn, address_summary_write_table_name)
########################

print("elapsed time = ", datetime.now() - datetimenow)