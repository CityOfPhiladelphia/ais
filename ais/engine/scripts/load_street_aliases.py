import sys
import traceback
from phladdress.data import DIRS_STD, SUFFIXES_STD
import datum
from ais import app
# DEV
from pprint import pprint


"""SET UP"""

config = app.config
source_def = config['BASE_DATA_SOURCES']['street_aliases']
source_db = datum.connect(config['DATABASES'][source_def['db']])
source_table = source_db[source_def['table']]
field_map = source_def['field_map']
db = datum.connect(config['DATABASES']['engine'])
alias_table = db['street_alias']


"""MAIN"""

print('Dropping indexes...')
alias_table.drop_index('seg_id')

print('Delete existing aliases...')
alias_table.delete()

print('Reading aliases from source...')
source_rows = source_table.read()
aliases = []

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
		aliases.append({
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

print('Writing aliases...')
alias_table.write(aliases)

print('Creating indexes...')
alias_table.create_index('seg_id')

db.save()
source_db.close()
db.close()
