import sys
from datetime import datetime
import datum
from ais import app
# DEV
import traceback
from pprint import pprint


start = datetime.now()
print('Starting...')

"""SET UP"""

config = app.config
db = datum.connect(config['DATABASES']['engine'])
poly_table = db['service_area_polygon']
line_single_table = db['service_area_line_single']
line_dual_table = db['service_area_line_dual']
layer_table = db['service_area_layer']
layers = config['SERVICE_AREAS']['layers']
geom_field = 'shape'
# sde_srid = 2272
WRITE_OUT = True

"""
TRANSFORMS

Define functions here that can be referenced in config.py for mutating
service area rows. Eventually, these could probably go in their own file
and be used by any script that iterates over rows dictionaries.

Args: row, value_field
Return: row
"""

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

print('\n** SERVICE AREA LAYERS **')

if WRITE_OUT:
	print('Deleting existing service area layers...')
	layer_table.delete()

	print('Writing service area layers...')
	keys = ['layer_id', 'name', 'description']
	layer_rows = [{key: layer[key] for key in keys} for layer in layers]
	db['service_area_layer'].write(layer_rows)

print('\n** SERVICE AREAS **')

if WRITE_OUT:
	print('Dropping indexes...')
	line_single_table.drop_index('seg_id')
	line_dual_table.drop_index('seg_id')

	print('Deleting existing service area polys...')
	poly_table.delete()
	print('Deleting existing service area single-value lines...')
	line_single_table.delete()
	print('Deleting existing service area dual-value lines...')
	line_dual_table.delete()

polys = []
line_singles = []
line_duals = []

print('Reading service areas...')
# wkt_field = geom_field + '_wkt'

for layer in layers:
	layer_id = layer['layer_id']
	print('  - {}'.format(layer_id))
	sources = layer['sources']

	# Check for conflicting source types
	if 'line_single' in sources and 'line_dual' in sources:
		raise Exception('Too many line sources for {}'.format(layer_id))

	for source_type, source in sources.items():
		# Connect to DB
		source_db_name = source['db']
		try:
			source_db = datum.connect(config['DATABASES'][source_db_name])
		except KeyError:
			print('Database {} not found'.format(layer_id))
			continue

		source_table_name = source['table']
		source_table = source_db[source_table_name]
		# import pdb; pdb.set_trace()
		source_geom_field = source_table.geom_field
		# If no object ID field is specified, default to `objectid`.
		object_id_field = source.get('object_id_field', 'objectid')
		
		# If there are transforms, reference their functions
		transforms = source.get('transforms', [])
		transform_map = {}
		for transform in transforms:
			f = getattr(sys.modules[__name__], transform)
			transform_map[transform] = f
		
		# POLYGON
		if source_type == 'polygon':
			value_field = source['value_field']
			source_fields = [value_field, object_id_field]
			source_rows = source_table.read(fields=source_fields, \
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

				poly = {
					'layer_id': 			layer_id,
					'source_object_id': 	source_row[object_id_field],
					'value': 				value or '',
					'geom': 				source_row[source_geom_field],
				}
				polys.append(poly)

		# LINE SINGLE
		if source_type == 'line_single':
			value_field = source['value_field']
			seg_id_field = source['seg_id_field']
			source_fields = [value_field, object_id_field, seg_id_field]
			source_rows = source_table.read(fields=source_fields)

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
			source_rows = source_table.read(fields=source_fields)

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
	poly_table.write(polys)

	print('Writing service area single-value lines...')
	line_single_table.write(line_singles)

	print('Writing service area line dual-value lines...')
	line_dual_table.write(line_duals)

	print('Creating indexes...')
	line_single_table.create_index('seg_id')
	line_dual_table.create_index('seg_id')

source_db.close()
db.close()
print('Finished in {} seconds'.format(datetime.now() - start))
