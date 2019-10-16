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

    if any(x_coord, y_coord) is None:
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
# ADDRESS AREA SUMMARY #
########################
print("Creating transformed address_summary table...")
address_summary_out_table = etl.fromdb(read_conn, 'select * from address_summary') \
    .addfield('address_full', (lambda a: make_address_full(
    {'address_low': a['address_low'], 'address_low_suffix': a['address_low_suffix'],
     'address_low_frac': a['address_low_frac'], 'address_high': a['address_high']}))) \
    .addfield('temp_lonlat', (lambda a: transform_coords({'geocode_x': a['geocode_x'], 'geocode_y': a['geocode_y']}))) \
    .addfield('geocode_lon', lambda a: a['temp_lonlat'][0]) \
    .addfield('geocode_lat', lambda a: a['temp_lonlat'][1]) \
    .cutout('temp_lonlat') \
    .fieldmap(mapping)

address_summary_out_table.tocsv("address_summary_transformed.csv", write_header=True)
address_summary_out_table.todb(read_conn, "address_summary_transformed", create=True, sample=0)
#########################
# DOR CONDOMINIUM ERROR #
#########################
print("Writing dor_condominium_error table...")
dor_condominium_error_table = etl.fromdb(read_conn, 'select * from dor_condominium_error') \
    .rename({'parcel_id': 'mapref', 'unit_num': 'condounit',}) \
    .tooraclesde(write_dsn, dor_condo_error_table_name)
###############################
# DOR PARCEL ADDRESS ANALYSIS #
###############################
# print("Performing dor_parcel address analysis...")
# import re
# from passyunk.parser import PassyunkParser
#
# street_name_re = re.compile('^[A-Z0-9 ]+$')
# unit_num_re = re.compile('^[A-Z0-9\-]+$')
# parser = PassyunkParser(MAX_RANGE=9999999)
#
# print('Reading streets...')
# street_rows = etl.fromdb(read_conn,
#                          'select street_full, seg_id, street_code, left_from, left_to, right_from, right_to from street_segment')
# street_code_map = {}  # street_full => street_code
# street_full_map = {}  # street_code => street_full
# seg_map = {}  # street_full => [seg rows]
# street_headers = street_rows[0]
# for street_row in street_rows[1:]:
#     street_row = dict(zip(street_headers, street_row))
#     street_code = street_row['street_code']
#     street_full = street_row['street_full']
#     seg_map.setdefault(street_full, [])
#     seg_map[street_full].append(street_row)
#     street_code_map[street_full] = street_code
#     street_full_map[street_code] = street_full
#
# street_code_map.update({
#     'VINE ST': 80120,
#     'MARKET ST': 53560,
#     'COMMERCE ST': 24500,
# })
# street_full_map.update({
#     80120: 'VINE ST',
#     53560: 'MARKET ST',
#     24500: 'COMMERCE ST',
# })
#
# source_def = config['BASE_DATA_SOURCES']['parcels']['dor']
# source_db_name = source_def['db']
# source_db_url = config['DATABASES']['doroem']
# parsed_dor_db_string = parse_url(source_db_url)
# read_dsn = parsed_dor_db_string['user'] + '/' + parsed_dor_db_string['password'] + '@' + parsed_dor_db_string['host']
# dsn = config['DATABASES']['engine']
# db_user = dsn[dsn.index("//") + 2:dsn.index(":", dsn.index("//"))]
# db_pw = dsn[dsn.index(":", dsn.index(db_user)) + 1:dsn.index("@")]
# db_name = dsn[dsn.index("/", dsn.index("@")) + 1:]
# pg_db = psycopg2.connect(
#     'dbname={db_name} user={db_user} password={db_pw} host=localhost'.format(db_name=db_name, db_user=db_user,
#                                                                              db_pw=db_pw))
# source_field_map = source_def['field_map']
# source_table_name = source_def['table']
# source_table_name = 'PARCEL'
# print(source_table_name)
# field_map = source_def['field_map']
# print("Reading, parsing, and analyzing dor_parcel components and writing to postgres...")
#
# etl.fromoraclesde(read_dsn, source_table_name, where="SDE.ST_ISEMPTY(SHAPE)=0") \
#     .cut('objectid', 'mapreg', 'stcod', 'house', 'suf', 'unit', 'stex', 'stdir', 'stnam',
#          'stdes', 'stdessuf', 'status', 'shape') \
#     .addfield('concatenated_address', lambda c: concatenate_dor_address(
#     {'house': c['house'], 'suf': c['suf'], 'stex': c['stex'], 'stdir': c['stdir'], 'stnam': c['stnam'],
#      'stdes': c['stdes'], 'stdessuf': c['stdessuf'], 'unit': c['unit'], 'stcod': c['stcod']})) \
#     .addfield('parsed_comps', lambda p: parser.parse(p['concatenated_address'])) \
#     .addfield('std_address_low', lambda a: a['parsed_comps']['components']['address']['low_num']) \
#     .addfield('std_address_low_suffix', lambda a: a['parsed_comps']['components']['address']['addr_suffix'] if
# a['parsed_comps']['components']['address']['addr_suffix'] else a['parsed_comps']['components']['address']['fractional']) \
#     .addfield('std_high_num', lambda a: a['parsed_comps']['components']['address']['high_num']) \
#     .addfield('std_street_predir', lambda a: a['parsed_comps']['components']['street']['predir']) \
#     .addfield('std_street_name', lambda a: a['parsed_comps']['components']['street']['name']) \
#     .addfield('std_street_suffix', lambda a: a['parsed_comps']['components']['street']['suffix']) \
#     .addfield('std_address_postdir', lambda a: a['parsed_comps']['components']['street']['postdir']) \
#     .addfield('std_unit_type', lambda a: a['parsed_comps']['components']['address_unit']['unit_type']) \
#     .addfield('std_unit_num', lambda a: a['parsed_comps']['components']['address_unit']['unit_num']) \
#     .addfield('std_street_address', lambda a: a['parsed_comps']['components']['output_address']) \
#     .addfield('std_street_code', lambda a: a['parsed_comps']['components']['street']['street_code']) \
#     .addfield('std_seg_id', lambda a: a['parsed_comps']['components']['cl_seg_id']) \
#     .addfield('cl_addr_match', lambda a: a['parsed_comps']['components']['cl_addr_match']) \
#     .cutout('parsed_comps') \
#     .addfield('no_address',
#               lambda a: 1 if standardize_nulls(a['stnam']) is None or standardize_nulls(a['house']) is None else None) \
#     .addfield('change_stcod', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['stcod'])) != str(
#     standardize_nulls(a['std_street_code'])) else None) \
#     .addfield('change_house', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['house'])) != str(
#     standardize_nulls(a['std_address_low'])) else None) \
#     .addfield('change_suf', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['suf'])) != str(
#     standardize_nulls(a['std_address_low_suffix'])) else None) \
#     .addfield('change_unit', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['unit'])) != str(
#     standardize_nulls(a['std_unit_num'])) else None) \
#     .addfield('change_stex', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['stex'])) != str(
#     standardize_nulls(a['std_high_num'])) else None) \
#     .addfield('change_stdir', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['stdir'])) != str(
#     standardize_nulls(a['std_street_predir'])) else None) \
#     .addfield('change_stnam', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['stnam'])) != str(
#     standardize_nulls(a['std_street_name'])) else None) \
#     .addfield('change_stdes', lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['stdes'])) != str(
#     standardize_nulls(a['std_street_suffix'])) else None) \
#     .addfield('change_stdessuf',
#               lambda a: 1 if a['no_address'] != 1 and str(standardize_nulls(a['stdessuf'])) != str(
#                   standardize_nulls(a['std_address_postdir'])) else 0) \
#     .tocsv('dor_parcel_address_analysis.csv', write_header=True)
# # get address_summary rows with dor_parcel_id as array:
# address_summary_rows = address_summary_out_table \
#     .addfield('dor_parcel_id_array', lambda d: d.dor_parcel_id.split('|') if d.dor_parcel_id else []) \
#     .addfield('opa_account_num_array', lambda d: d.opa_account_num.split('|') if d.opa_account_num else [])
# dor_parcel_address_analysis = etl.fromcsv('dor_parcel_address_analysis.csv')
# mapreg_count_map = {}
# address_count_map = {}
# dor_parcel_header = dor_parcel_address_analysis[0]
#
# # count_maps
# for row in dor_parcel_address_analysis[1:]:
#     dict_row = dict(zip(dor_parcel_header, row))
#     mapreg = dict_row['mapreg']
#     std_street_address = dict_row['std_street_address']
#     if mapreg not in mapreg_count_map:
#         mapreg_count_map[mapreg] = 1
#     else:
#         mapreg_count_map[mapreg] += 1
#     if std_street_address not in address_count_map:
#         address_count_map[std_street_address] = 1
#     else:
#         address_count_map[std_street_address] += 1
#
# # mapreg_opa_map
# mapreg_opa_map = {}
# address_summary_header = address_summary_rows[0]
# for i, row in enumerate(address_summary_rows[1:]):
#     if i % 1000 == 0:
#         print(i)
#     dict_row = dict(zip(address_summary_header, row))
#     opa_account_nums = dict_row['opa_account_num_array']
#     dor_parcel_ids = dict_row['dor_parcel_id_array']
#     for dor_parcel_id in dor_parcel_ids:
#         if dor_parcel_id not in mapreg_opa_map:
#             mapreg_opa_map[dor_parcel_id] = []
#         for opa_account_num in opa_account_nums:
#             if opa_account_num not in mapreg_opa_map[dor_parcel_id]:
#                 mapreg_opa_map[dor_parcel_id].append(opa_account_num)
#
# for k in mapreg_opa_map:
#     mapreg_opa_map[k] = '|'.join(mapreg_opa_map[k])
#
# dor_report_rows = dor_parcel_address_analysis\
#     .addfield('opa_account_nums', lambda o: mapreg_opa_map.get(o.mapreg,'')) \
#     .addfield('num_parcels_w_mapreg', lambda o: mapreg_count_map.get(o.mapreg, 0)) \
#     .addfield('num_parcels_w_address', lambda o: address_count_map.get(o.std_street_address, 0))
#
# # Write to local db
# dor_report_rows.topostgis(pg_db, 'dor_parcel_address_analysis')
###########################################################
#  Use The-el from here to write spatial tables to oracle #
###########################################################
print("Writing spatial reports to DataBridge...")
oracle_conn_gis_ais = config['ORACLE_CONN_GIS_AIS']
postgis_conn = config['POSTGIS_CONN']
subprocess.check_call(['./output_spatial_tables.sh', str(postgis_conn), str(oracle_conn_gis_ais)])
print("Cleaning up...")
# cur = read_conn.cursor()
# cur.execute('DROP TABLE "address_summary_transformed";')
# read_conn.commit()
read_conn.close()
