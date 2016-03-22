import sys
from phladdress.parser import Parser
from db.connect import connect_to_db
from config import CONFIG
# DEV
import traceback
from pprint import pprint

'''
CONFIG
'''

source_db = connect_to_db(CONFIG['db']['ais_source'])
ais_db = connect_to_db(CONFIG['db']['ais_work'])
source_table = 'CURBS_NO_CARTWAYS'
field_map = {'curb_id': 'CP_ID'}
source_srid = 2272
source_geom_field = 'SHAPE'
curb_table = 'curb'

'''
SET UP
'''

wkt_field = '{}_WKT'.format(source_geom_field)

'''
MAIN
'''

parser = Parser()

print('Dropping parcel-curb view...')
ais_db.drop_mview('parcel_curb')

print('Deleting existing curbs...')
ais_db.truncate('curb')

print('Reading curbs from source...')
source_fields = [field_map[x] for x in field_map]
source_rows = source_db.read(source_table, source_fields, \
	geom_field=source_geom_field)
row_fields = source_fields + [wkt_field]
curbs = []
for source_row in source_rows:
	curb = {x: source_row[field_map[x]] for x in field_map}
	curb['geometry'] = source_row[wkt_field]
	curbs.append(curb)

print('Writing curbs...')
ais_db.bulk_insert(curb_table, curbs, geom_field='geometry', \
	from_srid=source_srid, chunk_size=50000)

print('Creating parcel-curb view...')
parcel_curb_select_stmt = '''
	select p.parcel_id as parcel_id, c.curb_id as curb_id
	from pwd_parcel p
	join curb c
	on ST_Intersects(p.geometry, c.geometry)
'''
ais_db.create_mview('parcel_curb', parcel_curb_select_stmt)

ais_db.close()