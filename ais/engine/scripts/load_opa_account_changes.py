import sys
import re
from datetime import datetime
from tracemalloc import start
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
	source_def = config['BASE_DATA_SOURCES']['opa_account_num_changes']
	source_db = datum.connect(config['DATABASES'][source_def['db']])
	source_table = source_db[source_def['table']]
	field_map = source_def['field_map']

	db = datum.connect(config['DATABASES']['engine'])
	opa_account_num_changes_table = db['opa_account_num_changes']

	"""MAIN"""

	# Get field names
	source_fields = list(field_map.values())
	print('Dropping index...')
	opa_account_num_changes_table.drop_index('pin')

	print('Deleting existing OPA account num changes...')
	opa_account_num_changes_table.delete()

	print('Reading OPA account num changes from source...')
	source_opa_account_num_changes = source_table.read(fields=source_fields)
	opa_account_num_changes = []
	for i, source_opa_account_num_change in enumerate(source_opa_account_num_changes):
		try:
			if i % 1000 == 0:
				print(i)

			# Get attrs
			pin = source_opa_account_num_change[field_map['pin']]
			old_account_num = source_opa_account_num_change[field_map['old_opa_account_num']]
			new_account_num = source_opa_account_num_change[field_map['new_opa_account_num']]

			opa_account_num_changes.append({
				'pin': pin,
				'old_opa_account_num': old_account_num,
				'new_opa_account_num': new_account_num,
			})

		except Exception as e:
			print(f'Error processing OPA account num change with PIN {source_opa_account_num_change.get(field_map["pin"], "N/A")}: {e}')
			traceback.print_exc()

	print("Writing OPA account num changes to database...")
	opa_account_num_changes_table.write(opa_account_num_changes)
	
	print('Creating indexes...')
	opa_account_num_changes_table.create_index('pin')
	opa_account_num_changes_table.create_index('old_opa_account_num')

	db.close()
	print('Finished in {} seconds'.format(datetime.now() - start))
