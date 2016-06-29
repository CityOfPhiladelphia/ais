import sys
import os
import csv
from copy import deepcopy
from datetime import datetime
from phladdress.parser import Parser
import datum
from ais import app
from ais.models import Address
# DEV
import traceback
from pprint import pprint

start = datetime.now()

"""SET UP"""

config = app.config
db = datum.connect(config['DATABASES']['engine'])
source_db = datum.connect(config['DATABASES']['gis'])
# source_table = source_db['usps_zip4s']
source_table = source_db['vw_usps_zip4s_ais']
field_map = {
	'usps_id':			'updatekey',
	'address_low':		'addrlow',
	'address_high':		'addrhigh',
	'address_oeb':		'addroeb',
	'street_predir':	'streetpre',
	'street_name':		'streetname',
	'street_suffix':	'streetsuff',
	'street_postdir':	'streetpost',
	'unit_type':		'addrsecondaryabbr',
	'unit_low':			'addrsecondarylow',
	'unit_high':		'addrsecondaryhigh',
	'unit_oeb':			'addrsecondaryoeb',
	'zip_code':			'zipcode',
	'zip_4_low':		'zip4low',
	'zip_4_high':		'zip4high',
}
numeric_fields = ['address_low', 'address_high']
zip_range_table = db['zip_range']
address_zip_table = db['address_zip']
WRITE_OUT = True

source_fields = [field_map[x] for x in field_map]
char_fields = [x for x in field_map if not x in numeric_fields]

"""MAIN"""

if WRITE_OUT:
	print('Dropping indexes...')
	zip_range_table.drop_index('street_address')

	print('Deleting existing zip ranges...')
	zip_range_table.delete()

print('Reading zip ranges from source...')
# TODO: currently filtering out alphanumeric addrlows
source_rows = source_table.read(fields=source_fields)

zip_ranges = []

for i, source_row in enumerate(source_rows):
	if i % 25000 == 0:
		print(i)

	zip_range = {x: source_row[field_map[x]] for x in field_map}

	# Default char fields to empty string
	for x in char_fields:
		if zip_range[x] is None:
			zip_range[x] = ''
	
	# Handle differing ZIP4 low/high
	zip_4_low = source_row[field_map['zip_4_low']]
	zip_4_high = source_row[field_map['zip_4_high']]
	if zip_4_low != zip_4_high:
		zip_4 = ''
	else:
		zip_4 = zip_4_low

	# Set ZIP4
	zip_range.pop('zip_4_low')
	zip_range.pop('zip_4_high')
	zip_range['zip_4'] = zip_4

	zip_ranges.append(zip_range)

if WRITE_OUT:
	print('Writing zip ranges to AIS...')
	zip_range_table.write(zip_ranges)

	print('Creating indexes...')
	zip_range_table.create_index('usps_id')


print('\n** RELATE TO ADDRESSES**')
print('Reading addresses...')
addresses = db['address'].read(fields=['street_address'])
addresses = [Address(x['street_address']) for x in addresses]

if WRITE_OUT:
	print('Dropping indexes...')
	address_zip_table.drop_index('street_address')
	address_zip_table.drop_index('usps_id')
	print('Dropping address-zips...')
	address_zip_table.delete()

# index zip ranges by street_full
street_full_fields = [
	'street_predir',
	'street_name',
	'street_suffix',
	'street_postdir',
]

# For checking alpha unit ranges
alpha_list = list(map(chr, range(65, 91)))
alpha_map = {alpha_list[i]: i + 1 for i in range(0, 26)}  # A => 1, Z => 26

GENERIC_UNITS = set(['#', 'APT', 'UNIT', 'STE'])

zip_map_no_units = {}		# street_full => [non-unit ranges]
zip_map_units = {}			# street_full => [unit ranges]
address_zips = []

print('Indexing zip ranges by street...')
for zip_range in zip_ranges:
	street_full = ' '.join([zip_range[x] for x in street_full_fields \
		if zip_range[x] != ''])
	if zip_range['unit_type'] != '':
		street_zip_ranges = zip_map_units.setdefault(street_full, [])
	else:
		street_zip_ranges = zip_map_no_units.setdefault(street_full, [])
	street_zip_ranges.append(zip_range)

# DEV
exact_count = 0
unit_num_count = 0
unit_alpha_count = 0

# Loop over addresses
for address in addresses:
	try:
		address_low = address.address_low
		address_high = address.address_high or address_low
		address_parity = address.parity
		street_address = address.street_address
		street_full = address.street_full
		unit_type = address.unit_type
		unit_num = address.unit_num

		matching_zip_range = None
		match_type = None

		# UNIT
		# TODO: handle unit types like REAR that don't have a unit num
		if unit_type and unit_num:
			try:
				street_zip_ranges = zip_map_units[street_full]
				
				# Determine unit character type
				# ex. numeric, alpha, alphanum
				if unit_num.isdigit():
					unit_char_type = 'num'
				# Only accepting single alpha units for now. Multiple will take
				# more handling logic.
				elif unit_num.isalpha() and len(unit_num) == 1:
					unit_char_type = 'alpha'
				else:
					raise ValueError('Unit format not recognized')

				for zip_range in street_zip_ranges:
					zip_unit_type = zip_range['unit_type']
					zip_unit_low = zip_range['unit_low']
					zip_unit_high = zip_range['unit_high']
					
					# Check if address matches
					if not (zip_range['address_low'] <= address_low and \
						address_high <= zip_range['address_high']):
						continue

					# Check if parity matches
					zip_address_parity = zip_range['address_oeb']
					if zip_address_parity not in ['B', address_parity]:
						continue

					# Check if unit type matches
					if unit_type != zip_unit_type and \
						not (unit_type in GENERIC_UNITS and \
						zip_unit_type in GENERIC_UNITS):
						continue

					# Get char type of unit range
					if zip_unit_low.isdigit() and zip_unit_high.isdigit():
						zip_unit_char_type = 'num'
					elif zip_unit_low.isalpha() and zip_unit_high.isalpha():
						zip_unit_char_type = 'alpha'
					else:
						# Unhandled unit char type
						continue

					# If the types don't match, continue
					if zip_unit_char_type != unit_char_type:
						continue

					# Case 1: numeric unit
					if unit_char_type == 'num':
						if zip_unit_low <= unit_num <= zip_unit_high:
							matching_zip_range = zip_range
							match_type = 'unit_numeric'
							unit_num_count += 1
							break

					# Case 2: alpha unit range
					elif unit_char_type == 'alpha' and \
						len(zip_unit_low) == 1 and len(zip_unit_high) == 1:
						try:
							unit_alpha_i = alpha_map[unit_num]
							zip_alpha_i_low = alpha_map[zip_unit_low]
							zip_alpha_i_high = alpha_map[zip_unit_high]
						except KeyError:
							print('Unhandled KeyError')

						if zip_alpha_i_low <= unit_alpha_i <= \
							zip_alpha_i_high:
							# print('we got an alpha match')
							# print(street_address)
							# print(zip_range)
							# sys.exit()
							matching_zip_range = zip_range
							match_type = 'unit_alpha'
							unit_alpha_count += 1
							break

			except ValueError:
				# This should only happen when we had an unrecognized unit
				# format. Ignore and try to match to base zip range.
				pass

			except KeyError:
				pass

		# NON-UNIT
		# Use this if statement and not an else, because we still want this to
		# run if the unit search didn't turn anything up.
		if matching_zip_range is None:
			try:
				street_zip_ranges = zip_map_no_units[street_full]
			except KeyError:
				raise ValueError('Not a USPS street')

			for zip_range in street_zip_ranges:
				# Check if parity matches
				zip_address_parity = zip_range['address_oeb']
				if zip_address_parity not in ['B', address_parity]:
					continue

				if zip_range['address_low'] <= address_low and \
					address_high <= zip_range['address_high']:
					matching_zip_range = zip_range

					# If there was a unit that we ignored, flag it
					if unit_type:
						match_type = 'ignore_unit'
					else:
						match_type = 'exact'

					exact_count += 1
					break

		if matching_zip_range:
			address_zips.append({
				'street_address':	street_address,
				'usps_id':			matching_zip_range['usps_id'],
				'match_type':		match_type,
			})

		else:
			raise ValueError('Could not match to a ZIP range')

	except ValueError as e:
		# FEEDBACK
		# print('{}: {}'.format(street_address, e))
		pass

print(len(address_zips))
print('num: ' + str(unit_num_count))
print('alpha: ' + str(unit_alpha_count))
print('exact: ' + str(exact_count))

if WRITE_OUT:
	print('Writing address-zips...')
	address_zip_table.write(address_zips, chunk_size=150000)
	print('Creating index...')
	address_zip_table.create_index('street_address')
	address_zip_table.create_index('usps_id')

################################################################################

source_db.close()
db.close()

print('Finished in {}'.format(datetime.now() - start))
