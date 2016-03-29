import sys
from phladdress.parser import Parser
import datum
from ais import app
# DEV
import traceback
from pprint import pprint


"""SET UP"""

config = app.config
source_def = config['BASE_DATA_SOURCES']['curbs']
source_db = datum.connect(config['DATABASES'][source_def['db']])
source_table = source_db[source_def['table']]
field_map = source_def['field_map']
db = datum.connect(config['DATABASES']['engine'])
curb_table = db['curb']
parcel_curb_table = db['parcel_curb']


"""MAIN"""

# print('Dropping parcel-curb view...')
# db.drop_mview('parcel_curb')

print('Dropping indexes...')
curb_table.drop_index('curb_id')
parcel_curb_table.drop_index('curb_id')
parcel_curb_table.drop_index('parcel_source', 'parcel_row_id')

print('Deleting existing curbs...')
curb_table.delete()

print('Reading curbs from source...')
source_rows = source_table.read()
curbs = []
for source_row in source_rows:
	curb = {x: source_row[field_map[x]] for x in field_map}
	# curb['geom'] = source_row[wkt_field]
	curbs.append(curb)

print('Writing curbs...')
curb_table.write(curbs)

print('Making parcel-curbs...')
for agency in config['BASE_DATA_SOURCES']['parcels']:
    print('  - ' + agency)
    # table_name = parcel_source_def['table']
    stmt = '''
        insert into parcel_curb (parcel_source, parcel_row_id, curb_id) (
          select
            '{agency}',
            p.parcel_id,
            c.curb_id
          from {agency}_parcel p
          join curb c
          on ST_Intersects(p.geom, c.geom)
        )
    '''.format(agency=agency)
    db.execute(stmt)
    db.save()

print('Creating indexes...')



db.close()
