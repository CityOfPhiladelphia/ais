import sys
from datetime import datetime
from phladdress.parser import Parser
from db.connect import connect_to_db
from config import CONFIG
# DEV
import traceback
from pprint import pprint

'''
CONFIG
'''

poly_table = 'service_area_polygon'
line_single_table = 'service_area_line_single'
line_dual_table = 'service_area_line_dual'
layer_table = 'service_area_layer'
layers = CONFIG['service_areas']['layers']
geom_field = CONFIG['service_areas']['geom_field']
default_object_id_field = 'objectid'
sde_srid = 2272
WRITE_OUT = True

'''
TRANSFORMS

Define functions here that can be referenced in config.py for mutating
service area rows. Eventually, these could probably go in their own file
and be used by any script that iterates over rows dictionaries.

Args: row, value_field
Return: row
'''

def convert_to_integer(row, value_field):
	value = row[value_field]
	int_value = int(value)
	row[value_field] = int_value
	return row

def remove_whitespace(row, value_field):
	value = row[value_field]
	no_whitespace = value.replace(' ', '')
	row[value_field] = no_whitespace
	return row

'''
SET UP
'''

start = datetime.now()
print('Starting...')
ais_db = connect_to_db(CONFIG['db']['ais_work'])

'''
SERVICE AREA LAYERS
'''
print('\n** SERVICE AREA LAYERS **')

if WRITE_OUT:
	print('Deleting existing service area layers...')
	ais_db.truncate(layer_table)

	print('Writing service area layers...')
	keys = ['layer_id', 'name', 'description']
	layer_rows = [{key: layer[key] for key in keys} for layer in layers]
	ais_db.bulk_insert('service_area_layer', layer_rows)

'''
SERVICE AREAS
'''
print('\n** SERVICE AREAS **')

if WRITE_OUT:
	print('Dropping indexes...')
	ais_db.drop_index(line_single_table, 'seg_id')
	ais_db.drop_index(line_dual_table, 'seg_id')

	print('Deleting existing service area polys...')
	ais_db.truncate(poly_table)
	print('Deleting existing service area single-value lines...')
	ais_db.truncate(line_single_table)
	print('Deleting existing service area dual-value lines...')
	ais_db.truncate(line_dual_table)

polys = []
line_singles = []
line_duals = []

print('Reading service areas...')
wkt_field = geom_field + '_wkt'

for layer in layers:
	layer_id = layer['layer_id']
	print('  - {}'.format(layer_id))
	sources = layer['sources']

	# Check for conflicting source types
	if 'line_single' in sources and 'line_dual' in sources:
		raise Exception('Too many line sources for {}'.format(layer_id))

	for source_type, source in sources.items():
		# Get attrs
		source_db_name = source['db']
		source_table = source['table']
		object_id_field = source.get('object_id_field', default_object_id_field)
		
		# If there are transforms, reference their functions
		transforms = source.get('transforms', [])
		transform_map = {}
		for transform in transforms:
			f = getattr(sys.modules[__name__], transform)
			transform_map[transform] = f
		
		# Connect to DB
		try:
			source_db = connect_to_db(CONFIG['db'][source_db_name])
		except KeyError:
			print('Database {} not found'.format(layer_id))
			continue

		# POLYGON
		if source_type == 'polygon':
			value_field = source['value_field']
			source_fields = [value_field, object_id_field]
			source_rows = source_db.read(source_table, source_fields, \
				geom_field=geom_field)

			for i, source_row in enumerate(source_rows):
				# Transform if necessary
				for f in transform_map.values():
					source_row = f(source_row, value_field)
				
				value = source_row[value_field]

				# Remove excess whitespace from strings. This isn't a transform
				# because we want to do it to all strings.
				if isinstance(value, str):
					value = value.strip()

				object_id = source_row[object_id_field]
				if not object_id:
					pprint(source_row)
					sys.exit()

				poly = {
					'layer_id': 			layer_id,
					'source_object_id': 	source_row[object_id_field],
					'value': 				value or '',
					'geometry': 			source_row[wkt_field],
				}
				polys.append(poly)

		# LINE SINGLE
		if source_type == 'line_single':
			value_field = source['value_field']
			seg_id_field = source['seg_id_field']
			source_fields = [value_field, object_id_field, seg_id_field]
			source_rows = source_db.read(source_table, source_fields)

			for i, source_row in enumerate(source_rows):
				# Transform if necessary
				for f in transform_map.values():
					source_row = f(source_row, value_field)

				value = source_row[value_field]

				# Remove excess whitespace from strings. This isn't a transform
				# because we want to do it to all strings.
				if isinstance(value, str):
					value = value.strip()

				line_single = {
					'layer_id': 			layer_id,
					'source_object_id': 	source_row[object_id_field],
					'seg_id':				source_row[seg_id_field],
					'value': 				value or '',
				}
				line_singles.append(line_single)

		# LINE DUAL
		if source_type == 'line_dual':
			left_value_field = source['left_value_field']
			right_value_field = source['right_value_field']
			seg_id_field = source['seg_id_field']
			source_fields = [
				left_value_field,
				right_value_field,
				object_id_field,
				seg_id_field
			]
			source_rows = source_db.read(source_table, source_fields)

			for i, source_row in enumerate(source_rows):
				# Transform if necessary
				for f in transform_map.values():
					source_row = f(source_row, value_field)

				left_value = source_row[left_value_field]
				right_value = source_row[right_value_field]

				line_dual = {
					'layer_id': 			layer_id,
					'source_object_id': 	source_row[object_id_field],
					'seg_id':				source_row[seg_id_field],
					'left_value': 			left_value or '',
					'right_value': 			right_value or '',
				}
				line_duals.append(line_dual)

if WRITE_OUT:
	print('Writing service area polygons...')
	ais_db.bulk_insert(poly_table, polys, geom_field='geometry', \
		from_srid=sde_srid)

	print('Writing service area single-value lines...')
	ais_db.bulk_insert(line_single_table, line_singles)

	print('Writing service area line dual-value lines...')
	ais_db.bulk_insert(line_dual_table, line_duals)

	print('Creating indexes...')
	ais_db.create_index(line_single_table, 'seg_id')
	ais_db.create_index(line_dual_table, 'seg_id')

source_db.close()
ais_db.close()
print('Finished in {} seconds'.format(datetime.now() - start))