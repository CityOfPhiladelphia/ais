import sys
import os
import csv
from datetime import datetime
from phladdress.parser import Parser
from db.connect import connect_to_db
from models.address import Address
from config import CONFIG
# DEV
from pprint import pprint
import traceback

start = datetime.now()
print('Starting...')


'''
CONFIG
'''

source_parcel_table = 'pwd_parcels'
field_map = {
	# AIS 				# Source
	'parcel_id': 		'PARCELID',
	'source_address': 	'ADDRESS',
	'source_brt_id': 	'BRT_ID',
}
source_geom_field = 'SHAPE'
source_srid = 2272
opa_view = 'VW_OPA_OWNERS'


'''
SET UP
'''

source_db = connect_to_db(CONFIG['db']['ais_source'])
ais_db = connect_to_db(CONFIG['db']['ais_work'])

# Read in OPA account nums and addresses
opa_rows = source_db.read(opa_view, ['ACCOUNT_NUM', 'STREET_ADDRESS'])
opa_map = {x['ACCOUNT_NUM']: x['STREET_ADDRESS'] for x in opa_rows}

# Make a list of non-unique addresses in PWD parcels. If a parcel has one of 
# these addresses, use OPA address instead. Case: 421 S 10TH ST appears three
# times in parcels but should have unit nums according to OPA.
print('Loading non-unique parcel addresses...')
ambig_stmt = '''
	select address
	from {}
	group by address
	having address is not null and count(*) > 1
'''.format(source_parcel_table)
source_db.c.execute(ambig_stmt)
ambig_rows = source_db.c.fetchall()
ambig_addresses = set([x[0] for x in ambig_rows])

'''
MAIN
'''

# Set up logging
LOG_COLS = [
	'parcel_id',
	'source_address',
	'error',
]
parent_dir = os.path.abspath(os.path.join(__file__, os.pardir))
log = open(parent_dir + '/log/load_pwd_parcels.log', 'w', newline='')
log_writer = csv.writer(log)
log_writer.writerow(LOG_COLS)

parser = Parser()

print('Dropping indexes...')
ais_db.drop_index('pwd_parcel', 'street_address')

print('Deleting existing parcels...')
ais_db.truncate('pwd_parcel')

# Get field names
source_parcel_id_field = field_map['parcel_id']
source_address_field = field_map['source_address']
source_brt_id_field = field_map['source_brt_id']
wkt_field = '{}_WKT'.format(source_geom_field)

# Read parcels
print('Reading parcels from source...')
source_fields = list(field_map.values())
source_parcels = source_db.read(source_parcel_table, source_fields, \
	geom_field=source_geom_field)
parcel_rows = []

# Loop over source parcels
for i, source_parcel in enumerate(source_parcels):
	try:
		if i % 50000 == 0:
			print(i)

		# Get attrs
		parcel_id = source_parcel[source_parcel_id_field]
		geometry = source_parcel[wkt_field]
		source_brt_id = source_parcel[source_brt_id_field]
		source_address = source_parcel[source_address_field]
		
		if source_address in (None, ''):
			raise ValueError('No address')

		# If there are multiple parcels with the same address, get OPA
		# address
		if source_address in ambig_addresses and source_brt_id in opa_map:
			source_address = opa_map[source_brt_id]

		try:
			address = Address(source_address)
		except:
			raise ValueError('Could not parse')

		parcel = address.as_dict()
		parcel.update({
			'geometry':		geometry,
			'parcel_id':	parcel_id,
		})
		parcel_rows.append(parcel)

		# FEEDBACK
		# if source_address != parcel.street_address:
		# 	print('{} => {}'.format(source_address, parcel.street_address))

	except ValueError as e:
		print('Parcel {}: {}'.format(parcel_id, e))
		log_writer.writerow([parcel_id, source_address, e])

	except Exception as e:
		print('{}: Unhandled error'.format(source_parcel))
		print(traceback.format_exc())

print('Writing parcels...')
ais_db.bulk_insert('pwd_parcel', parcel_rows, geom_field='geometry', \
	from_srid=source_srid, chunk_size=50000)
# ais_db.save()

print('Creating indexes...')
ais_db.create_index('pwd_parcel', 'street_address')

source_db.close()
ais_db.close()
log.close()
print('Finished in {} seconds'.format(datetime.now() - start))
print('Wrote {} parcels'.format(len(parcels)))