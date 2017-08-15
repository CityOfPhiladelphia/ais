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
# true_range_in_table = etl.fromdb(read_conn, 'select * from true_range')
# # print(etl.look(true_range_in_table))
# etl.tooraclesde(true_range_in_table, write_dsn, true_range_write_table_name)
# ########################
# # SERVICE AREA SUMMARY #
# ########################
# service_area_summary_in_table = etl.fromdb(read_conn, 'select * from service_area_summary')
# # print(etl.look(service_area_summary_in_table))
# etl.tooraclesde(service_area_summary_in_table, write_dsn, service_area_summary_write_table_name)
# ########################
# # ADDRESS AREA SUMMARY #
# ########################
# address_summary_in_table = etl.fromdb(read_conn, 'select * from address_summary')
# address_summary_out_table = address_summary_in_table \
#     .addfield('address_full', (lambda a: make_address_full({'address_low': a['address_low'], 'address_low_suffix': a['address_low_suffix'], 'address_low_frac': a['address_low_frac'], 'address_high': a['address_high']}))) \
#     .addfield('temp_lonlat', (lambda a: transform_coords({'geocode_x': a['geocode_x'], 'geocode_y': a['geocode_y']}))) \
#     .addfield('geocode_lon', lambda a: a['temp_lonlat'][0]) \
#     .addfield('geocode_lat', lambda a: a['temp_lonlat'][1]) \
#     .addfield('shape', lambda a: a['temp_lonlat'][2]) \
#     .cutout('temp_lonlat') \
#     .fieldmap(mapping)
#
# # print(etl.look(address_summary_out_table))
# etl.tooraclesde(address_summary_out_table, write_dsn, address_summary_write_table_name)
########################
# DOR PARCEL ERROR
########################
# dor_dsn = 'gis_dor/deed@gis'
# dor_conn = cx_Oracle.connect(dor_dsn)
# dor_parcel_error_write_table_name = 'DOR_PARCEL_ERROR'
# print(dor_conn)
# # dor_parcel_csv_path = 'c:/projects/etl/dor_parcel.csv'
# # dor_parcel_shape_in_table = etl.fromcsv(dor_parcel_csv_path).cut('MAPREG', 'SHAPE').rename({'MAPREG': 'mapreg', 'SHAPE': 'shape'})
# # print(etl.look(dor_parcel_shape_in_table))
# # raise
# # dor_parcel_error_in_table = etl.fromdb(read_conn, 'select * from dor_parcel_error where length(mapreg) > 1')
# dor_parcel_error_in_table = etl.fromdb(read_conn, 'select * from dor_parcel_error').rename({'level': 'level_', 'objectid': 'source_objid'})
# # join_error_table = etl.join(dor_parcel_error_in_table, dor_parcel_shape_in_table, key='mapreg')
# # print(etl.nrows(join_error_table))
# # print(etl.look(join_error_table))
#
# etl.tooraclesde(dor_parcel_error_in_table, write_dsn, dor_parcel_error_write_table_name)

########################
# PWD PARCEL ERROR
########################
# pwd_parcel_error_csv_path = 'C:/Users/Alex.Waldman/Desktop/Projects Sandbox/ais/analysis/pwd_parcels not in ais_20170803.csv'
# pwd_parcel_error_write_table_name = 'PWD_PARCEL_ERROR'
# pwd_parcel_error_in_table = etl.fromcsv(pwd_parcel_error_csv_path)
# print(etl.look(pwd_parcel_error_in_table))
# # join_error_table = etl.join(dor_parcel_error_in_table, dor_parcel_shape_in_table, key='mapreg')
# # print(etl.nrows(join_error_table))
# # print(etl.look(join_error_table))
#
# etl.tooraclesde(pwd_parcel_error_in_table, write_dsn, pwd_parcel_error_write_table_name)
# print("elapsed time = ", datetime.now() - datetimenow)
########################
# DOR PARCEL ERROR
########################
import re
from passyunk.data import DIRS_STD, SUFFIXES_STD
from passyunk.parser import PassyunkParser
from petl import header

street_name_re = re.compile('^[A-Z0-9 ]+$')
unit_num_re = re.compile('^[A-Z0-9\-]+$')
parser = PassyunkParser()

print('Reading streets...')
street_rows = etl.fromdb(read_conn,
                         'select street_full, seg_id, street_code, left_from, left_to, right_from, right_to from street_segment')
street_code_map = {}  # street_full => street_code
street_full_map = {}  # street_code => street_full
seg_map = {}  # street_full => [seg rows]
street_headers = street_rows[0]
for street_row in street_rows[1:]:
    street_row = dict(zip(street_headers, street_row))
    street_code = street_row['street_code']
    street_full = street_row['street_full']

    seg_map.setdefault(street_full, [])
    seg_map[street_full].append(street_row)

    street_code_map[street_full] = street_code
    street_full_map[street_code] = street_full

street_code_map.update({
    'VINE ST': 80120,
    'MARKET ST': 53560,
    'COMMERCE ST': 24500,
})
street_full_map.update({
    80120: 'VINE ST',
    53560: 'MARKET ST',
    24500: 'COMMERCE ST',
})


def standardize_nulls(val):
    if type(val) == str:
        return None if val.strip() == '' else val
    else:
        return None if val == 0 else val

def make_concatenated_dor_address(source_comps):
    ## For now don't clean up components to illustrate state in concatenated address
    # for field, value in source_comps.items():
    #     if isinstance(value, str):
    #         value = value.strip()
    #         if len(value) == 0 or value == '0':
    #             value = None
    #             source_comps[field] = value
    #     elif value == 0:
    #         source_comps[field] = None
    # print(source_comps)

    # Get attributes
    address_low = source_comps[field_map['address_low']]
    address_low_suffix = source_comps[field_map['address_low_suffix']]
    address_high = source_comps[field_map['address_high']]
    street_predir = source_comps[field_map['street_predir']]
    street_name = source_comps[field_map['street_name']]
    street_suffix = source_comps[field_map['street_suffix']]
    street_postdir = source_comps[field_map['street_postdir']]
    unit_num = source_comps[field_map['unit_num']]
    street_code = source_comps[field_map['street_code']]
    # Declare this here so the except clause doesn't bug out
    source_address = None
    street_full = ''
    # Make street full
    if street_name:
        street_comps = [street_predir, street_name, street_suffix, \
                        street_postdir]
        street_full = ' '.join([x for x in street_comps if x])

    address_low_fractional = None
    if address_low_suffix == '2':
        address_low_fractional = '1/2'
        address_low_suffix = None
    #
    # # Handle ranges
    # if address_low and address_high:
    #     address_low_str = str(address_low)
    #     address_high_str = str(address_high)
    #     len_address_low = len(address_low_str)
    #     len_address_high = len(address_high_str)
    #     address_high_full = None
    #
    #     if not address_high_str.isnumeric():
    #         address_high = None
    #
    #     if address_high:
    #         # Case: 1234-36 or 1234-6
    #         if len_address_high < len_address_low:
    #             # Make address high full and compare to address low
    #             address_high_prefix = address_low_str[:-len_address_high]
    #             address_high_full = int(address_high_prefix + address_high_str)
    #         # Cases: 1234-1236 or 2-12
    #         elif len_address_low == len_address_high or \
    #                 (len_address_low == 1 and len_address_high == 2):
    #             address_high_full = address_high
    #
    #         # Case: 317-315
    #         if address_high_full:
    #             # Make sure both addresses are on the same hundred block
    #             address_high = str(address_high_full)[-2:]

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


source_def = config['BASE_DATA_SOURCES']['parcels']['dor']
source_db_name = source_def['db']
# source_db_url = config['DATABASES'][source_db_name]
source_db_url = config['DATABASES']['doroem']
parsed_dor_db_string = parse_url(source_db_url)
# print(parsed_dor_db_string)
read_dsn = parsed_dor_db_string['user'] + '/' + parsed_dor_db_string['password'] + '@' + parsed_dor_db_string['host']
dsn = config['DATABASES']['engine']
db_user = dsn[dsn.index("//") + 2:dsn.index(":", dsn.index("//"))]
db_pw = dsn[dsn.index(":",dsn.index(db_user)) + 1:dsn.index("@")]
db_name = dsn[dsn.index("/", dsn.index("@")) + 1:]
pg_db = psycopg2.connect('dbname={db_name} user={db_user} password={db_pw} host=localhost'.format(db_name=db_name, db_user=db_user, db_pw=db_pw))

source_field_map = source_def['field_map']
# source_table_name = source_def['table']
source_table_name = 'PARCEL'
# print(source_table_name)
field_map = source_def['field_map']
print("Reading, parsing, and analyzing dor_parcel components and writing to db...")

dor_table_address_analysis = etl.fromoraclesde(read_dsn, source_table_name) \
    .cut('objectid', 'mapreg', 'stcod', 'house', 'suf', 'unit', 'stex', 'stdir', 'stnam',
                                  'stdes', 'stdessuf', 'shape') \
    .select(lambda c: standardize_nulls(c['stnam']) is not None and standardize_nulls(c['house'] is not None)) \
    .addfield('concatenated_address', lambda c: make_concatenated_dor_address(
    {'house': c['house'], 'suf': c['suf'], 'stex': c['stex'], 'stdir': c['stdir'], 'stnam': c['stnam'],
     'stdes': c['stdes'],
     'stdessuf': c['stdessuf'], 'unit': c['unit'], 'stcod': c['stcod']})) \
    .addfield('parsed_comps', lambda p: parser.parse(p['concatenated_address'])) \
    .addfield('std_address_low', lambda a: a['parsed_comps']['components']['address']['low_num']) \
    .addfield('std_address_low_suffix', lambda a: a['parsed_comps']['components']['address']['addr_suffix']) \
    .addfield('std_high_num', lambda a: a['parsed_comps']['components']['address']['high_num']) \
    .addfield('std_street_predir', lambda a: a['parsed_comps']['components']['street']['predir']) \
    .addfield('std_street_name', lambda a: a['parsed_comps']['components']['street']['name']) \
    .addfield('std_street_suffix', lambda a: a['parsed_comps']['components']['street']['suffix']) \
    .addfield('std_address_postdir', lambda a: a['parsed_comps']['components']['street']['postdir']) \
    .addfield('std_unit_type', lambda a: a['parsed_comps']['components']['address_unit']['unit_type']) \
    .addfield('std_unit_num', lambda a: a['parsed_comps']['components']['address_unit']['unit_num']) \
    .addfield('std_street_address', lambda a: a['parsed_comps']['components']['output_address']) \
    .addfield('std_street_code', lambda a: a['parsed_comps']['components']['street']['street_code']) \
    .addfield('std_seg_id', lambda a: a['parsed_comps']['components']['cl_seg_id']) \
    .addfield('cl_addr_match', lambda a: a['parsed_comps']['components']['cl_addr_match']) \
    .cutout('parsed_comps') \
    .addfield('change_stcod', lambda a: 1 if str(standardize_nulls(a['stcod'])) != str(a['std_street_code']) else 0) \
    .addfield('change_house', lambda a: 1 if str(standardize_nulls(a['house'])) != str(a['std_address_low']) else 0) \
    .addfield('change_suf', lambda a: 1 if str(standardize_nulls(a['suf'])) != str(a['std_address_low_suffix']) else 0) \
    .addfield('change_unit', lambda a: 1 if str(standardize_nulls(a['unit'])) != str(a['std_unit_num']) else 0) \
    .addfield('change_stex', lambda a: 1 if str(standardize_nulls(a['stex'])) != str(a['std_high_num']) else 0) \
    .addfield('change_stdir', lambda a: 1 if str(standardize_nulls(a['stdir'])) != str(a['std_street_predir']) else 0) \
    .addfield('change_stnam', lambda a: 1 if str(standardize_nulls(a['stnam'])) != str(a['std_street_name']) else 0) \
    .addfield('change_stdes', lambda a: 1 if str(standardize_nulls(a['stdes'])) != str(a['std_street_suffix']) else 0) \
    .addfield('change_stdessuf',
              lambda a: 1 if str(standardize_nulls(a['stdessuf'])) != str(a['std_address_postdir']) else 0) \
    .progress(10000) \
    .select(lambda d: 1 in [d['change_stcod'], d['change_house'], d['change_suf'], d['change_unit'],
                            d['change_stex'], d['change_stdir'], d['change_stnam'], d['change_stdes'],
                            d['change_stdessuf']
                            or d['cl_addr_match'] != 'A']) \
    .cut('objectid', 'mapreg', 'stcod', 'house', 'suf', 'unit', 'stex', 'stdir', 'stnam', 'stdes', 'stdessuf',
         'concatenated_address', 'std_street_address', 'std_address_low', 'std_address_low_suffix', 'std_high_num',
         'std_street_predir', 'std_street_name', 'std_street_suffix', 'std_address_postdir', 'std_unit_type',
         'std_unit_num', 'std_street_code', 'std_seg_id', 'cl_addr_match', 'change_stcod', 'change_house', 'change_suf',
         'change_unit', 'change_stex', 'change_stdir', 'change_stnam', 'change_stdes', 'change_stdessuf',
         'shape') \
    .topostgis(pg_db, 'dor_parcel_address_comp_analysis')

# print(etl.look(dor_table_address_analysis))
