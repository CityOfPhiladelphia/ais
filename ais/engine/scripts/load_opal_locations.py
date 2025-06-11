from datetime import datetime
import datum
from ais import app

def main():
    print('Starting...')
    start = datetime.now()

    """SET UP"""
    config = app.config
    source_def = config['BASE_DATA_SOURCES']['opal_locations']
    source_db = datum.connect(config['DATABASES'][source_def['db']])
    source_table = source_db[source_def['table']]
    field_map = source_def['field_map']
    db = datum.connect(config['DATABASES']['engine'])
    opal_table = db['opal_locations']

    Parser = config['PARSER']
    parser = Parser()

    """MAIN"""
    
    print('Dropping index...')
    opal_table.drop_index('location_id')

    print('Deleting existing OPAL locations...')
    opal_table.delete()

    print('Reading OPAL locations from source...')
    source_rows = source_table.read()
    opal_locations = []
    for source_row in source_rows:
        opal_loc = {x: source_row[field_map[x]] for x in field_map}
        # TODO: passyunk parse 
        full_source_address_raw = ' '.join([opal_loc['address_line_1'], opal_loc['address_line_2']]).strip()
        try:
            parsed = parser.parse(full_source_address_raw)
            parsed_addr = parsed['components']['output_address']
            if parsed['type'] != 'address':
                raise ValueError('Invalid address')
            opal_loc['street_address'] = parsed_addr

            if opal_loc['is_ship_to'] == 'Y':
                opal_loc['location_usage'] = 'ship-to'
            elif opal_loc['is_business_site'] == 'Y' and opal_loc['is_business_asset'] == 'Y':
                opal_loc['location_usage'] = 'both'
            elif opal_loc['is_business_site'] == 'Y':
                opal_loc['location_usage'] = 'business-site'
            elif opal_loc['is_business_asset'] == 'Y':
                opal_loc['location_usage'] = 'business_asset'
            else:
                raise ValueError("Location does not have a usage!")

            OPAL_FINAL_COLS = [
                'id', 'location_id', 'location_name', 'street_address', 
                'superior_location', 'location_type', 'location_usage', 'ship_to_location_id'
                ]
            opal_loc = {k:v for k,v in opal_loc.items() if k in OPAL_FINAL_COLS}

            opal_locations.append(opal_loc)
        except Exception as e:
            print(f"could not parse {full_source_address_raw} ({e})")
            pass

    print('Writing OPAL locations...')
    opal_table.write(opal_locations)

    print('Creating index...')
    opal_table.create_index('location_id')

    db.close()
    runtime = datetime.now() - start
    print(f'Finished in {runtime} seconds')