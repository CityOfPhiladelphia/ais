import sys
import re
from datetime import datetime
from phladdress.parser import Parser
import datum
from ais import app
from ais.models import Address
# DEV
import traceback
from pprint import pprint


print('Starting...')
start = datetime.now()


"""SET UP"""

config = app.config
source_def = config['BASE_DATA_SOURCES']['properties']
source_db = datum.connect(config['DATABASES'][source_def['db']])
source_table = source_db[source_def['table']]
field_map = source_def['field_map']
db = datum.connect(config['DATABASES']['engine'])
prop_table = db['opa_property']

'''
MAIN
'''

parser = Parser()

# Get field names
source_fields = list(field_map.values())
source_tencode_field = field_map['tencode']
source_account_num_field = field_map['account_num']
source_address_field = field_map['source_address']
source_address_suffix_field = field_map['address_suffix']
source_unit_field = field_map['unit']

print('Dropping index...')
prop_table.drop_index('street_address')

print('Deleting existing properties...')
prop_table.delete()

print('Reading owners from source...')
owner_stmt = '''
	select p.parcelno, o.owners
	from BRT_ADMIN.properties p
	left join BRT_ADMIN.PROPERTIES_OWNERS po on p.propertyid = po.PROPERTYID
	left join (
		select propertyid, listagg(trim(name), '|')
		within group(order by propertyid) as owners
		from brt_admin.owners
		group by propertyid) o on o.propertyid = po.propertyid
	group by p.parcelno, o.owners
'''
owner_rows = source_db.execute(owner_stmt)

sys.exit()
owner_map = {x[0]: x[1] for x in owner_rows}

print('Reading properties from source...')
source_props = source_db.read(source_table, source_fields)
props = []

for i, source_prop in enumerate(source_props):
	try:
		if i % 100000 == 0:
			print(i)

		# Get attrs
		tencode = source_prop[source_tencode_field]
		account_num = source_prop[source_account_num_field]
		location = source_prop[source_address_field]
		unit = source_prop[source_unit_field]
		address_suffix = source_prop[source_address_suffix_field]

		# Handle address
		source_address = location.strip()
		if unit:
			unit = unit.lstrip('0')  # Remove leading zeros from unis
			source_address = '{} #{}'.format(source_address, unit)

		# Append address suffix (e.g. 101A)
		if address_suffix and address_suffix.isalpha():
			if not re.match('\d+[A-Z]', source_address):
				# FEEDBACK: missing suffix
				if '-' in source_address:
					insert_i = source_address.index('-')
				else:
					insert_i = source_address.index(' ')
				source_address = source_address[:insert_i] + address_suffix + \
					source_address[insert_i:]

		# Parse
		try:
			parsed = parser.parse(source_address)
			comps = parsed['components']
		except:
			raise ValueError('Could not parse')
		address = Address(comps)
		street_address = comps['street_address']

		# Owners
		try:
			owners = owner_map[account_num]
		except KeyError:
			owners = ''

		prop = {
			'account_num': account_num,
			'source_address': source_address,
			'tencode': tencode,
			'owners': owners,
			'address_low': comps['address']['low_num'],
			'address_low_suffix': comps['address']['low_suffix'] or '',
			'address_low_fractional': comps['address']['low_fractional'] or '',
			'address_high': comps['address']['high_num_full'],
			'street_predir': comps['street']['predir'] or '',
			'street_name': comps['street']['name'],
			'street_suffix': comps['street']['suffix'] or '',
			'street_postdir': comps['street']['postdir'] or '',
			'unit_num': comps['unit']['num'] or '',
			'unit_type': comps['unit']['type'] or '',
			'street_address': street_address,
		}
		props.append(prop)

	except ValueError as e:
		# FEEDBACK
		pass

	except Exception as e:
		print('Unhandled exception on {}'.format(source_address))
		print(traceback.format_exc())
		# sys.exit()

print('Writing properties...')
db.bulk_insert(prop_table, props, chunk_size=50000)

print('Creating index...')
db.create_index(prop_table, 'street_address')

'''
FINISH
'''

source_db.close()
db.close()
print('Finished in {} seconds'.format(datetime.now() - start))
