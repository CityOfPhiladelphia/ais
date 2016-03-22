import sys
from datetime import datetime
from shapely.wkt import loads
from datetime import datetime
from phladdress.parser import Parser
from copy import deepcopy
from db.connect import connect_to_db
from models.address import Address
from config import CONFIG
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

'''
CONFIG
'''

sa_layer_defs = CONFIG['service_areas']['layers']
sa_layer_ids = [x['layer_id'] for x in sa_layer_defs]
poly_table = 'service_area_polygon'
line_single_table = 'service_area_line_single'
line_dual_table = 'service_area_line_dual'
sa_summary_table = 'service_area_summary'
address_summary_table = 'address_summary'
address_summary_fields = [
	'street_address',
	'geocode_x',
	'geocode_y',
	# 'seg_id',
	# 'seg_side',
]
WRITE_OUT = True

'''
SET UP
'''

ais_db = connect_to_db(CONFIG['db']['ais_work'])
sa_summary_fields = [{'name': 'street_address', 'type': 'character varying(255)'}]
sa_summary_fields += [{'name': x, 'type': 'character varying(255)'} for x in sa_layer_ids]
sa_summary_row_template = {x: '' for x in sa_layer_ids}

# Keep poly rows in memory so we make less trips to the database for overlapping
# points.
xy_map = {}  # x => y => [sa_poly_rows]

'''
MAIN
'''

if WRITE_OUT:
	print('Dropping service area summary table...')
	ais_db.drop_table(sa_summary_table)

	print('Creating service area summary table...')
	ais_db.create_table(sa_summary_table, sa_summary_fields)

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
address_summary_rows = ais_db.read(address_summary_table, \
	address_summary_fields)

sa_summary_rows = []

for i, address_summary_row in enumerate(address_summary_rows):
	try:
		if i % 25000 == 0:
			print(i)

			# Write in chunks
			if WRITE_OUT: #and i % 50000 == 0:
				ais_db.bulk_insert(sa_summary_table, sa_summary_rows)
				sa_summary_rows = []

		# Get attributes
		street_address = address_summary_row['street_address']
		# seg_id = address_summary_row['seg_id']
		# seg_side = address_summary_row['seg_side']
		x = address_summary_row['geocode_x']
		y = address_summary_row['geocode_y']

		sa_rows = None
		if x in xy_map:
			y_map = xy_map[x]
			if y in y_map:
				sa_rows = y_map[y]

		if sa_rows is None:
			# Get intersecting service areas
			where = 'ST_Intersects(geometry, ST_SetSrid(ST_Point({}, {}), 2272))'.format(x, y)
			sa_rows = ais_db.read(poly_table, ['layer_id', 'value'], where=where)

			# Add to map
			x_map = xy_map[x] = {}
			x_map[y] = sa_rows
		
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

	except:
		print(traceback.format_exc())
		sys.exit()

# Clear out XY map
xy_map = {}

if WRITE_OUT:
	print('Writing service area summary rows...')
	ais_db.bulk_insert(sa_summary_table, sa_summary_rows)
	del sa_summary_rows

################################################################################
# SERVICE AREA LINES
################################################################################

if WRITE_OUT:
	print('\n** SERVICE AREA LINES ***\n')
	print('Creating indexes...')
	ais_db.create_index(sa_summary_table, 'street_address')

	print('Creating temporary indexes...')
	ais_db.create_index(address_summary_table, 'seg_id')

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
			ais_db.c.execute(stmt)
			print(ais_db.c.rowcount)
			ais_db.save()

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
			ais_db.c.execute(stmt)
			print(ais_db.c.rowcount)
			ais_db.save()

	print('Dropping temporary index...')
	ais_db.drop_index(address_summary_table, 'seg_id')

ais_db.close()

print('Finished in {}'.format(datetime.now() - start))