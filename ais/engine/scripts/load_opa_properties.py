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
    source_def = config['BASE_DATA_SOURCES']['properties']
    source_db = datum.connect(config['DATABASES'][source_def['db']])
    ais_source_db = datum.connect(config['DATABASES']['citygeo'])
    source_table = source_db[source_def['table']]
    field_map = source_def['field_map']

    owner_source_def = config['BASE_DATA_SOURCES']['opa_owners']
    owner_table_name = owner_source_def['table']

    db = datum.connect(config['DATABASES']['engine'])
    prop_table = db['opa_property']

    Parser = config['PARSER']
    parser = Parser()

    """MAIN"""

    # Get field names
    source_fields = list(field_map.values())
    source_tencode_field = field_map['tencode']
    source_account_num_field = field_map['account_num']
    source_address_field = field_map['source_address']

    print('Dropping index...')
    prop_table.drop_index('street_address')

    print('Deleting existing properties...')
    prop_table.delete()

    print('Reading owners from source...')
    owner_stmt = """
    select account_num, owners from {}
    """.format(owner_table_name)
    print(owner_stmt)
    owner_rows = ais_source_db.execute(owner_stmt)
    owner_map = {x['account_num']: x['owners'] for x in owner_rows}

    print('Reading properties from source...')
    source_props = source_table.read(fields=source_fields)
    props = []

    for i, source_prop in enumerate(source_props):
        try:
            if i % 100000 == 0:
                print(i)

            # Get attrs
            tencode = source_prop[source_tencode_field]
            account_num = source_prop[source_account_num_field]
            location = source_prop[source_address_field]

            # Handle address
            source_address = location.strip()

            # Parse
            try:
                parsed = parser.parse(source_address)
                comps = parsed['components']
            except:
                raise ValueError('Could not parse')
            address = Address(parsed)
            street_address = comps['output_address']

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
            props.append(prop)

        # except ValueError as e:
        #     # FEEDBACK
        #     pass

        except Exception as e:
            print('Unhandled exception on {}'.format(source_address))
            print(traceback.format_exc())
            raise e

    print('Writing properties...')
    prop_table.write(props)

    print('Creating index...')
    prop_table.create_index('street_address')

    '''
    FINISH
    '''

    db.close()
    print('Finished in {} seconds'.format(datetime.now() - start))
