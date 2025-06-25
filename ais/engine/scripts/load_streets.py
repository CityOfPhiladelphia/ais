import sys
import traceback
from datetime import datetime
from pprint import pprint
# from phladdress.parser import Parser
from ais import app
from datum import Database
from ais.models import StreetSegment

def main():
    print('Starting...')
    start = datetime.now()

    """SET UP"""

    config = app.config

    Parser = config['PARSER']

    db = Database(config['DATABASES']['engine'])
    engine_srid = config['ENGINE_SRID']

    # Get table params
    source_def = config['BASE_DATA_SOURCES']['streets']
    source_db_name = source_def['db']
    source_db_url = config['DATABASES'][source_db_name]
    field_map = source_def['field_map']
    source_table_name = source_def['table']
    street_full_fields = ['street_' + x for x in ['predir', 'name', 'suffix', 'postdir']]
    source_street_full_fields = [field_map[x] for x in street_full_fields]

    # Get table references
    source_db = Database(source_db_url)
    source_table = source_db[source_table_name]
    source_geom_field = source_table.geom_field
    street_table_name = StreetSegment.__table__.name
    street_table = db[street_table_name]


    """MAIN"""

    parser = Parser()

    print('Deleting existing streets...')
    street_table.delete(cascade=True)

    print(f'Reading streets table {source_table} from source...')
    source_fields = list(field_map.values())
    source_rows = source_table.read(to_srid=engine_srid)
    print('Rows retrieved.')

    streets = []
    error_count = 0

    # Loop over streets
    for i, source_row in enumerate(source_rows):
        try:
            if i % 10000 == 0:
                print(i)

            # Parse street name
            source_street_full_comps = [str(source_row[x]).strip() for x in \
                source_street_full_fields]
            # source_street_full_comps = [x for x in source_street_full_comps if x != '']
            source_street_full_comps = [x for x in source_street_full_comps if x not in ('', None, 'None')]
            source_street_full = ' '.join(source_street_full_comps)
            seg_id = source_row[field_map['seg_id']]
            try:
                parsed = parser.parse(source_street_full)
                if parsed['type'] != 'street':
                    raise ValueError('Invalid street')
                comps = parsed['components']['street']    # <== passyunk
            except Exception as e:
                print(f'Could not parse {source_street_full}')
                pass

            # Check for unaddressable streets
            left_to = source_row[field_map['left_to']]
            right_to = source_row[field_map['right_to']]
            if left_to == 0 and right_to == 0:
                raise ValueError('Not a range')

            street_suffix = comps['suffix']
            if street_suffix == 'RAMP':
                pass

            street_comps = {
                'street_predir': comps['predir'] or '',
                'street_name': comps['name'] or '',
                'street_suffix': comps['suffix'] or '',
                'street_postdir': comps['postdir'] or '',
                'street_full': comps['full'],
            }

            # Get values
            street = {key: source_row[value] for key, value in field_map.items()}
            street.update(street_comps)
            street['geom'] = source_row[source_geom_field]
            streets.append(street)

        except ValueError as e:
            error_count += 1

        except Exception as e:
            print(f'Unhandled error on row: {i}')
            print(traceback.format_exc())
            raise e

    '''
    WRITE
    '''

    street_table.write(streets, chunk_size=50000)

    '''
    FINISH
    '''

    print(f'{error_count} errors')
    db.close()
    print(f'Finished in {datetime.now() - start} seconds')
