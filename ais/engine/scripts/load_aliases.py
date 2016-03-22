import sys
import traceback
from phladdress.data import DIRS_STD, SUFFIXES_STD
from db.connect import connect_to_db
from config import CONFIG
# DEV
from pprint import pprint

'''
CONFIG
'''

# This is a map of all non-geometry fields. Geometry is handled separately.
field_map = {
	# Destination				# Source
	'seg_id':					'SEG_ID',
	'street_predir':			'PRE_DIR',
	'street_name':				'NAME',
	'street_suffix':			'TYPE',
	'street_postdir':			'SUF_DIR',
}
alias_table = 'street_alias'
source_db = connect_to_db(CONFIG['db']['ais_source'])
ais_db = connect_to_db(CONFIG['db']['ais_work'])

'''
MAIN
'''

# Delete existing
print('Delete existing aliases...')
ais_db.truncate('street_alias')

# Read aliases
print('Reading aliases from source...')
source_fields = list(field_map.values())
source_rows = source_db.read('ALIAS_LIST', source_fields)
insert_rows = []

# Loop over aliases
for i, alias_row in enumerate(source_rows):
	try:
		# Get attrs
		predir = alias_row[field_map['street_predir']]
		name = alias_row[field_map['street_name']]
		suffix = alias_row[field_map['street_suffix']]
		postdir = alias_row[field_map['street_postdir']]

		street_fields = ['street_' + x for x in ['predir', 'name', 'suffix', 'postdir']]
		source_comps = [alias_row[field_map[x]] for x in street_fields]
		source_comps = [x if x else '' for x in source_comps]
		source_street_full = ' '.join([x for x in source_comps if x])

		# Make sure attrs are standardizable
		invalid_predir = (predir and not predir in DIRS_STD)
		invalid_suffix = (suffix and suffix not in SUFFIXES_STD)
		invalid_postdir = (postdir and not postdir in DIRS_STD)
		if any([invalid_predir, invalid_suffix, invalid_postdir]):
			raise ValueError('Invalid alias: {}'.format(source_street_full))

		# Standardize
		predir = DIRS_STD[predir] if predir else None
		suffix = SUFFIXES_STD[suffix] if suffix else None
		postdir = DIRS_STD[postdir] if postdir else None

		# Get values
		insert_rows.append({
			'seg_id': alias_row[field_map['seg_id']],
			'street_predir': predir or '',
			'street_name': name,
			'street_suffix': suffix or '',
			'street_postdir': postdir or '',
		})

	except ValueError:
		# TODO: FEEDBACK
		pass

	except:
		print(alias_row)
		print(traceback.format_exc())
		sys.exit()

ais_db.bulk_insert(alias_table, insert_rows)
ais_db.save()

'''
FINISH
'''

source_db.close()
ais_db.close()