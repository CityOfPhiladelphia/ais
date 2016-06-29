import sys
from datetime import datetime
from shapely.wkt import loads
from datetime import datetime
from copy import deepcopy
import datum
from ais import app
from ais.models import Address

# DEV
import traceback
from pprint import pprint


print('Starting...')
start = datetime.now()

"""
TODO
- This might perform better if we do one big spatial join at the beginning
  between address summary and service area polygons.
"""

"""SET UP"""
config = app.config
db = datum.connect(config['DATABASES']['engine'])
sa_layer_defs = config['SERVICE_AREAS']['layers']
sa_layer_ids = [x['layer_id'] for x in sa_layer_defs]
poly_table = db['service_area_polygon']
line_single_table = db['service_area_line_single']
line_dual_table = db['service_area_line_dual']
sa_summary_table = db['service_area_summary']
address_summary_table = db['address_summary']
address_summary_fields = [
	'street_address',
	'geocode_x',
	'geocode_y',
	# 'seg_id',
	# 'seg_side',
]
sa_summary_fields = [{'name': 'street_address', 'type': 'text'}]
sa_summary_fields += [{'name': x, 'type': 'text'} for x in sa_layer_ids]
sa_summary_row_template = {x: '' for x in sa_layer_ids}

# DEV
WRITE_OUT = True

# Keep poly rows in memory so we make less trips to the database for overlapping
# points.
# xy_map = {}  # x => y => [sa_poly_rows]

"""MAIN"""

if WRITE_OUT:
	print('Dropping service area summary table...')
	db.drop_table('service_area_summary')

	print('Creating service area summary table...')
	db.create_table('service_area_summary', sa_summary_fields)

# print('Reading single-value service area lines...')
# line_single_map = {}  # layer_id => seg_id => value
# line_singles = ais_db.read(line_single_table, ['*'])

# for line_single in line_singles:
# 	layer_id = line_single['layer_id']
# 	seg_id = line_single['seg_id']
# 	value = line_single['value']
# 	if layer_id not in line_single_map:
# 		line_single_map[layer_id] = {}
# 	line_single_map[layer_id][seg_id] = value

# print('Reading dual-value service area lines...')
# line_dual_map = {}  # layer_id => seg_id => value
# line_duals = ais_db.read(line_dual_table, ['*'])

# for line_dual in line_duals:
# 	layer_id = line_dual['layer_id']
# 	seg_id = line_dual['seg_id']
# 	left_value = line_dual['left_value']
# 	right_value = line_dual['right_value']
# 	if layer_id not in line_dual_map:
# 		line_dual_map[layer_id] = {}

# 	line_dual_map[layer_id][seg_id] = {}
# 	line_dual_map[layer_id][seg_id]['left'] = left_value
# 	line_dual_map[layer_id][seg_id]['right'] = right_value

print('Reading address summary...')
address_summary_rows = address_summary_table.read(\
	fields=address_summary_fields, \
	sort=['geocode_x', 'geocode_y']\
)

sa_summary_rows = []

# Sort address summary rows by X, Y and use these to compare the last row
# to the current one. This minimizes trips to the database for poly values.
last_x = None
last_y = None
last_sa_rows = None

print('Intersecting addresses and service area polygons...')
for i, address_summary_row in enumerate(address_summary_rows):
	try:
		if i % 10000 == 0:
			print(i)

			# Write in chunks
			if WRITE_OUT: #and i % 50000 == 0:
				sa_summary_table.write(sa_summary_rows)
				sa_summary_rows = []

		# Get attributes
		street_address = address_summary_row['street_address']
		# seg_id = address_summary_row['seg_id']
		# seg_side = address_summary_row['seg_side']
		x = address_summary_row['geocode_x']
		y = address_summary_row['geocode_y']

		sa_rows = None
		# if x in xy_map:
		# 	y_map = xy_map[x]
		# 	if y in y_map:
		# 		sa_rows = y_map[y]
		if last_x and (last_x == x and last_y == y):
			sa_rows = last_sa_rows

		if sa_rows is None:
			# Get intersecting service areas
			where = 'ST_Intersects(geom, ST_SetSrid(ST_Point({}, {}), 2272))'.format(x, y)
			sa_rows = poly_table.read(fields=['layer_id', 'value'], where=where)

			# Add to map
			# x_map = xy_map[x] = {}
			# x_map[y] = sa_rows
		
		# Create and insert summary row
		sa_summary_row = deepcopy(sa_summary_row_template)
		sa_summary_row['street_address'] = street_address
		update_dict = {x['layer_id']: x['value'] for x in sa_rows}
		sa_summary_row.update(update_dict)

		# Override poly values with values from lines
		# if seg_id:
		# 	# Line single
		# 	for layer_id in line_single_map:
		# 		if seg_id in line_single_map[layer_id]:
		# 			value = line_single_map[layer_id][seg_id]
		# 			sa_summary_row[layer_id] = value

		# 	# Line dual
		# 	for layer_id in line_dual_map:
		# 		if 

		sa_summary_rows.append(sa_summary_row)

		last_x = x
		last_y = y
		last_sa_rows = sa_rows

	except:
		print(traceback.format_exc())
		sys.exit()

# Clear out XY map
xy_map = {}

if WRITE_OUT:
	print('Writing service area summary rows...')
	sa_summary_table.write(sa_summary_rows)
	del sa_summary_rows

################################################################################
# SERVICE AREA LINES
################################################################################

if WRITE_OUT:
	print('\n** SERVICE AREA LINES ***\n')
	print('Creating indexes...')
	sa_summary_table.create_index('street_address')

	print('Creating temporary indexes...')
	address_summary_table.create_index('seg_id')

	for sa_layer_def in sa_layer_defs:
		layer_id = sa_layer_def['layer_id']

		if 'line_single' in sa_layer_def['sources']:
			print('Updating from {}...'.format(layer_id))
			stmt = '''
				UPDATE service_area_summary sas
				SET {layer_id} = sals.value
				FROM address_summary ads, service_area_line_single sals
				WHERE
					sas.street_address = ads.street_address AND 
					sals.seg_id = ads.seg_id AND
					sals.layer_id = '{layer_id}' AND
					sals.value <> ''
			'''.format(layer_id=layer_id)
			db.execute(stmt)
			# print(ais_db.c.rowcount)
			db.save()

		elif 'line_dual' in sa_layer_def['sources']:
			print('Updating from {}...'.format(layer_id))
			stmt = '''
				UPDATE service_area_summary sas
				SET {layer_id} = CASE WHEN (ads.seg_side = 'L') THEN sald.left_value ELSE sald.right_value END
				FROM address_summary ads, service_area_line_dual sald
				WHERE sas.street_address = ads.street_address AND
					sald.seg_id = ads.seg_id AND
					sald.layer_id = '{layer_id}' AND
					CASE WHEN (ads.seg_side = 'L') THEN sald.left_value ELSE sald.right_value END <> ''
			'''.format(layer_id=layer_id)
			db.execute(stmt)
			# print(ais_db.c.rowcount)
			db.save()

	print('Dropping temporary index...')
	address_summary_table.drop_index('seg_id')

db.close()

print('Finished in {}'.format(datetime.now() - start))