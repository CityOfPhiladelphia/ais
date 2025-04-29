import sys
import re
from datetime import datetime
import datum
from ais import app
from ais.models import Address
# DEV
import traceback
from pprint import pprint

def main():

	print('Starting...')
	start = datetime.now()

	"""SET UP"""

	config = app.config
	source_def = config['BASE_DATA_SOURCES']['ng911_address_points']
	source_db = datum.connect(config['DATABASES'][source_def['db']])
	source_table = source_db[source_def['table']]

	field_map = source_def['field_map']
	source_where = source_def['where']

	db = datum.connect(config['DATABASES']['engine'])
	ng911_table = db['ng911_address_point']

	Parser = config['PARSER']
	parser = Parser()

	"""MAIN"""

	# Get field names
	source_fields = list(field_map.values())
	source_guid_field = field_map['guid']
	source_address_field = field_map['source_address']
	source_placement_type_field = field_map['placement_type']
	source_geom_field = field_map['geom'] # moved to account for datum postgis differences from oracle

	print('Dropping index...')
	ng911_table.drop_index('street_address')

	print('Deleting existing NG911 address points...')
	ng911_table.delete()

	print('Reading NG911 address points from source...')
	source_address_points = source_table.read(fields=source_fields, where=source_where)
	address_points = []

	for i, source_address_point in enumerate(source_address_points):
		try:
			if i % 100000 == 0:
				print(i)

			# Get attrs
			guid = source_address_point[source_guid_field]
			placement_type = source_address_point[source_placement_type_field]
			location = source_address_point[source_address_field]
			geometry = source_address_point[source_geom_field]

			# Handle address
			source_address = location.strip()

			if source_address in (None, ''):
				raise ValueError('No address')

			# Parse
			try:
				parsed = parser.parse(source_address)
				comps = parsed['components']
			except:
				raise ValueError('Could not parse')
			address = Address(parsed)
			street_address = comps['output_address']

			address_point = {
				'guid': guid,
				'source_address': source_address,
				'placement_type': placement_type,
				'geom': geometry,
				'address_low': comps['address']['low_num'],
				'address_low_suffix': comps['address']['addr_suffix'] or '',
				'address_high': comps['address']['high_num_full'],
				'street_predir': comps['street']['predir'] or '',
				'street_name': comps['street']['name'],
				'street_suffix': comps['street']['suffix'] or '',
				'street_postdir': comps['street']['postdir'] or '',
				'unit_num': comps['address_unit']['unit_num'] or '',
				'unit_type': comps['address_unit']['unit_type'] or '',
				'street_address': street_address,
			}
			address_points.append(address_point)

		except ValueError as e:
			# FEEDBACK
			print("value error...")
			pass

		except Exception as e:
			print('Unhandled exception on {}'.format(source_address))
			print(traceback.format_exc())
			# sys.exit()

	print('Writing {} NG911 address points...'.format(len(address_points)))
	ng911_table.write(address_points)

	print('Creating index...')
	ng911_table.create_index('street_address')

	'''
	FINISH
	'''

	db.close()
	print('Finished in {} seconds'.format(datetime.now() - start))