import petl as etl
import cx_Oracle
import psycopg2
from datetime import datetime
from ais import app


start = datetime.now()
print('Starting...')

"""SET UP"""

config = app.config
engine_dsn = config['DATABASES']['engine']
db_user = engine_dsn[engine_dsn.index("//") + 2:engine_dsn.index(":", engine_dsn.index("//"))]
db_pw = engine_dsn[engine_dsn.index(":",engine_dsn.index(db_user)) + 1:engine_dsn.index("@")]
db_name = engine_dsn[engine_dsn.index("/", engine_dsn.index("@")) + 1:]
pg_db = psycopg2.connect('dbname={db_name} user={db_user} password={db_pw} host=localhost'.format(db_name=db_name, db_user=db_user, db_pw=db_pw))
source_def = config['BASE_DATA_SOURCES']['condos']['dor']
source_db_name = source_def['db']
source_db_url = config['DATABASES'][source_db_name]
dsn = source_db_url.split('//')[1].replace(':','/')
dbo = cx_Oracle.connect(dsn)
source_table_name = source_def['table']
source_field_map = source_def['field_map']
source_field_map_upper = {}

for k,v in source_field_map.items():
    source_field_map_upper[k] = v.upper()

# Read DOR CONDO rows from source
print("Reading condos...")
# TODO: get fieldnames from source_field_map
read_stmt = '''
    select condounit, objectid, mapref from {dor_condo_table}
    where status in (1,3)
'''.format(dor_condo_table = source_table_name)
source_dor_condo_rows = etl.fromdb(dbo, read_stmt).fieldmap(source_field_map_upper)
print(etl.look(source_dor_condo_rows))

# Read DOR Parcel rows from engine db
print("Reading parcels...")
read_stmt = '''
    select parcel_id, street_address, address_low, address_low_suffix, address_low_frac, address_high, street_predir, 
    street_name, street_suffix, street_postdir, street_full from {dor_parcel_table} where parcel_id not in (
select parcel_id from 
(select parcel_id, count(*) as count from {dor_parcel_table} group by parcel_id) foo
where count > 1
)
'''.format(dor_parcel_table='dor_parcel')
engine_dor_parcel_rows = etl.fromdb(pg_db, read_stmt)
print(etl.look(engine_dor_parcel_rows))

# Get address comps for condos by joining to dor_parcel on parcel_id
print("Relating condos to parcels...")
joined = etl.join(source_dor_condo_rows, engine_dor_parcel_rows, key='parcel_id') \
    .convert('street_address', lambda a, row: row.street_address + ' # ' + row.unit_num, pass_row=True)
print(etl.look(joined))

# Write to engine db
print('Writing condos...')
# joined.todb(pg_db, 'dor_condominium')

# Calculate errors
joined_ids = joined.cut('source_object_id')
source_ids = source_dor_condo_rows.cut('source_object_id')
error_ids = etl.complement(source_ids, joined_ids)

print(etl.look(error_ids))
error_ids.tocsv('dor_condo_error_objectids.csv')

