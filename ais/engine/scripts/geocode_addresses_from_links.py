from datetime import datetime
import datum
from ais import app

start = datetime.now()
print('Starting...')

'''
SET UP
'''

config = app.config
Parser = config['PARSER']
parser = Parser()
db = datum.connect(config['DATABASES']['engine'])
WRITE_OUT = True
geocode_table = db['geocode']
address_tag_table = db['address_tag']
geocode_tag_map = {
    'pwd_parcel_id': (1, 3, 7, 11),
    'dor_parcel_id': (2, 4, 8, 12)
}
new_geocode_rows = []

print('Reading geocode rows...')
geocode_map = {}
geocode_rows = geocode_table.read()
print('Mapping geocode rows...')
for geocode_row in geocode_rows:
    street_address = geocode_row['street_address']
    if not street_address in geocode_map:
        geocode_map[street_address] = []
    geocode_map[street_address].append(geocode_row)

print('Reading address tags...')
tag_map = {}
where = "linked_address != '' and key in ('pwd_parcel_id', 'dor_parcel_id')"
tag_rows = address_tag_table.read(where=where)
print('Mapping address tags...')
for tag_row in tag_rows:
    street_address = tag_row['street_address']
    if not street_address in tag_map:
        tag_map[street_address] = []
    tag_map[street_address].append(tag_row)

for key, value in tag_map.items():
    street_address = key
    tags = value
#    geocode_types = []
    try:
        geocode_types = [x['geocode_type'] for x in geocode_map[street_address]]
    except:
        geocode_types = []
    for tag in tags:
        linked_address = tag['linked_address']
        linked_key = tag['key']
        if linked_key == 'pwd_parcel_id' and 1 in geocode_types or linked_key == 'dor_parcel_id' and 2 in geocode_types:
            continue
        try:
            linked_geocode_rows = geocode_map[linked_address]
        except:
            linked_geocode_rows = []
        if not linked_geocode_rows:
            continue
        for linked_row in linked_geocode_rows:
            geocode_type = linked_row['geocode_type']

            if geocode_type in geocode_tag_map[linked_key]:
                geom = linked_row['geom']
                new_geocode_row = {
                    'street_address': street_address,
                    'geocode_type': geocode_type,
                    'geom': geom
                }
                new_geocode_rows.append(new_geocode_row)

# Remove any duplicate new_geocode_rows
new_geocode_rows = [dict(t) for t in set([tuple(d.items()) for d in new_geocode_rows])]

if WRITE_OUT:
    print('Dropping indexes...')
    geocode_table.drop_index('street_address')

    print('Writing {num} new geocode rows...'.format(num=len(new_geocode_rows)))
    # TODO: Use geopetl/datum instead of raw sql
    i = 0
    values = ''
    for new_row in new_geocode_rows:
        street_address = new_row['street_address']
        geocode_type = new_row['geocode_type']
        geom = new_row['geom']
        new_vals = '''('{street_address}', {geocode_type}, '{geom}')'''.format(street_address=street_address, geocode_type=geocode_type, geom=geom)
        values = values + ', ' + new_vals if values else new_vals
        i += 1
        if i % 1000 == 0:
            toi = i + 1000
            #print("writing rows {i} to {toi}".format(i=i, toi=toi))
            write_stmt = '''
                INSERT INTO geocode (street_address, geocode_type, geom) VALUES {values}
            '''.format(values=values)
            db.execute(write_stmt)
            db.save()
            values = ''

    print('Creating index...')
    geocode_table.create_index('street_address')

db.close()

print('Finished in {}'.format(datetime.now() - start))
