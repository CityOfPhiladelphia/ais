from datetime import datetime
import datum
from ais import app
import petl as etl
import os
import psutil

def copy(db, out_file: str, query: str): 
    '''Run a postgres COPY command with the database and query specified to out_file'''
    with open(out_file, 'w') as out_file: 
        db._c.copy_expert(query, out_file)

def cleanup(filename: str): 
    '''Print the virtual memory consumption and remove the downloaded file'''
    print(psutil.virtual_memory())
    os.remove(filename)
    print(f'Removed {filename}')

def create_map(rows, map_name: str, column_name: str, map_dict: dict) -> dict: 
    '''
    Read a csv and create a dictionary mapping where the keys are the unique 
    values in column "column_name" and the values are a list of matching table rows.
    To append to an existing mapping, pass it to map_dict.
    '''
    i = -1
    for i, row in enumerate(rows):
        value = row[column_name]
        if not value in map_dict:
            map_dict[value] = []
        map_dict[value].append(row)
    if i > -1: # Used to prevent an error if rows == []
        print(f"length {map_name}: {len(map_dict)}. Total values looped through: {i + 1}")
    return map_dict

def main():
    WRITE_OUT = True

    start = datetime.now()
    print('Starting at ', start)

    config = app.config
    Parser = config['PARSER']
    parser = Parser()
    db = datum.connect(config['DATABASES']['engine'])
    address_tag_table = db['address_tag']
    tag_fields = config['ADDRESS_SUMMARY']['tag_fields']
    geocode_where = "WHERE geocode_type in (1,2)"

    print('Deleting linked tags...')
    del_stmt = '''
        Delete from address_tag where linked_address != ''
    '''
    db.execute(del_stmt)
    db.save()

    print('Reading address links...')
    address_link_file = 'address_link.csv'
    query = f"copy (select * from address_link) TO STDOUT WITH CSV HEADER;"
    copy(db, address_link_file, query)
    link_map = create_map(
        rows=etl.fromcsv(address_link_file).dicts(), 
        map_name='link_map', column_name='address_1', map_dict={})
    cleanup(address_link_file)

    print('Reading address tags')
    address_tag_file = 'address_tag.csv'
    query = f"copy (select * from address_tag) TO STDOUT WITH CSV HEADER;"
    copy(db, address_tag_file, query)
    tag_map = create_map(
        rows=etl.fromcsv(address_tag_file).dicts(), 
        map_name='tag_map', column_name='street_address', map_dict={})
    cleanup(address_tag_file)

    print('Reading geocode rows...')
    geocode_file = 'geocode.csv'
    query = f"copy (select * from geocode {geocode_where}) TO STDOUT WITH CSV HEADER;"
    copy(db, geocode_file, query)
    
    geocode_map = {}
    rows = etl.fromcsv(geocode_file).dicts()
    for row in rows:
        street_address = row['street_address']
        if not street_address in geocode_map:
            geocode_map[street_address] = {'pwd': '', 'dor': ''}
        if row['geocode_type'] == 1:
            geocode_map[street_address]['pwd'] = row['geom']
        else:
            geocode_map[street_address]['dor'] = row['geom']
    print(f"length geocode_map: {len(geocode_map)}")
    cleanup(geocode_file)
    
    #define traversal order
    traversal_order = ['has generic unit', 'matches unit', 'has base', 'overlaps', 'in range']
    
    print('Reading addresses...')
    address_file = 'address.csv'
    query = f"copy (select * from address) TO STDOUT WITH CSV HEADER;"
    copy(db, address_file, query)
    address_rows = etl.fromcsv(address_file).dicts()

    print('Making linked tags...')
    linked_tags_map = []
    new_linked_tags = []
    i = 1
    done = False

    rejected_link_map = {}

    while not done:

        print("Linked tags iteration: ", i)

        # add new tags to tag map
        tag_map = create_map(
            rows=new_linked_tags, map_name='tag_map', column_name='street_address', 
            map_dict=tag_map)

        new_linked_tags = []
        # loop through addresses
        for address_row in address_rows:
            street_address = address_row['street_address']
            # get address tags associated with street address
            mapped_tags = tag_map.get(street_address)
            links = link_map.get(street_address)
            # sort links by traversal order
            sorted_links = []
            if links:
                for rel in traversal_order:
                    for link in links:
                        if link['relationship'] == rel:
                            sorted_links.append(link)
                            # links.remove(link)
            # loop through tag fields in config
            for tag_field in tag_fields:
                found = False
                # Skip tag_fields where 'traverse_links' value is false
                if tag_field['traverse_links'] != 'true':
                    continue
                tag_key = tag_field['tag_key']
                # Look for tag in tag_map for street_address
                tag_value = None
                # Check if already have value for this tag
                if mapped_tags:
                    mapped_tags_for_key = [mapped_tag for mapped_tag in mapped_tags if mapped_tag.get('key', '') == tag_key]
                    first_mapped_tag_for_key = sorted(mapped_tags_for_key, key=lambda s: s['value'])[0] if mapped_tags_for_key else None
                    if first_mapped_tag_for_key:
                        tag_value = first_mapped_tag_for_key['value']
                        found = True
                # Otherwise, look for tag in address links
                if not links or found:
                    # Do something if tag can't be found by traversing links so API doesn't look for it
                    continue
                # loop through links
                for slink in sorted_links:
                    if found == True:
                        break
                    link_address = slink.get('address_2')
                    # Don't allow tags from links with different non-null pwd or dor geocoded geoms:
                    if all(a in geocode_map for a in (link_address, street_address)):
                        # TODO: different constraints based on tag type (i.e. dor/pwd ids)
                        # if either parcel geocodes have different geoms don't inherit:
                        if (geocode_map[link_address]['pwd'] is not None and geocode_map[link_address]['pwd'] != geocode_map[street_address]['pwd']) and \
                        (geocode_map[link_address]['dor'] is not None and geocode_map[link_address]['dor'] != geocode_map[street_address]['dor']):
                            if street_address not in rejected_link_map:
                                rejected_link_map[street_address] = []
                            rejected_link_map[street_address].append(link_address)
                            continue

                    # get tags for current link
                    link_tags = tag_map.get(link_address)
                    if link_tags:
                        link_tags_for_key = [link_tag for link_tag in link_tags if link_tag.get('key', '') == tag_key]
                        first_link_tag_for_key = sorted(link_tags_for_key, key=lambda s: s['value'])[0] if link_tags_for_key else None
                        if first_link_tag_for_key:
                            tag_value = first_link_tag_for_key['value']
                            link_path = slink['relationship']
                            linked_path = first_link_tag_for_key['linked_path'] if first_link_tag_for_key['linked_path'] else link_address
                            linked_address = first_link_tag_for_key['linked_address'] if first_link_tag_for_key['linked_address'] else link_address
                            linked_path = street_address + ' ' + link_path + ' ' + linked_path
                            add_tag_dict = {'street_address': street_address, 'key': tag_key, 'value': tag_value,
                                            'linked_address': linked_address, 'linked_path': linked_path}
                            new_linked_tags.append(add_tag_dict)
                            found = True

        if len(new_linked_tags) > 0:
            linked_tags_map = linked_tags_map + new_linked_tags
        else:
            done = 'done'
        i += 1

    """WRITE OUT"""

    if WRITE_OUT:
        print('Writing ', len(linked_tags_map), ' linked tags to address_tag table...')
        address_tag_table.write(linked_tags_map, chunk_size=150000)
        print('Rejected links: ')
        for key, value in rejected_link_map.items():
            value=list(set(value))
            print('{key}: {value}'.format(key=key, value=value))

    # Finally, loop through addresses one last time checking for tags with keys not in tag table, and for each tag lookup
    # tag linked_addresses in address_link table address_2 for street_address having unit type & num matching the current
    # loop address.
    print("Searching for linked tags via path: has base in range unit child")
    new_linked_tags = []

    print("Reading addresses...")
    address_file = 'address.csv'
    query = f"copy (select * from address where unit_num != '' order by street_address) TO STDOUT WITH CSV HEADER;"
    copy(db, address_file, query)
    address_rows = etl.fromcsv(address_file).dicts()

    print('Reading address tags...')
    tag_map = {}
    tag_sel_stmt = '''
        select a.*, t.key, t.value, t.linked_address, t.linked_path
        from (
          select street_address
          from address
          where unit_num != '')
          a
        left join address_tag t on t.street_address = a.street_address
        order by a.street_address, t.key, t.value
    '''
    tag_rows = db.execute(tag_sel_stmt)
    tag_map = create_map(
        rows=tag_rows, map_name='tag_map', column_name='street_address', map_dict={})

    print('Reading address links...')
    link_sel_stmt = '''
        select al.*
        from (
            SELECT *
            from address
            where address_high is not Null) a
        inner join address_link al on al.address_2 = a.street_address
        where relationship = 'has base'
        order by address_1
    '''
    link_rows = db.execute(link_sel_stmt) # Change to copy
    link_map = create_map(
        rows=link_rows, map_name='link_map', column_name='address_2', map_dict={})

    i=0
    rejected_link_map = {}
    print('Looping through {} addresses...'.format(len(address_rows))) # Remove this
    for address_row in address_rows:
        i+=1
        unit_num = address_row['unit_num']
        street_address = address_row['street_address']
        low_num = address_row['address_low']
        unit_type = address_row['unit_type']
        street_predir = address_row['street_predir']
        street_name = address_row['street_name']
        street_suffix = address_row['street_suffix']
        street_postdir = address_row['street_postdir']
        low_num = low_num if low_num else ''
        unit_type = unit_type if unit_type else ''
        unit_num = unit_num if unit_num else ''
        street_name = street_name if street_name else ''
        street_predir = street_predir if street_predir else ''
        street_suffix = street_suffix if street_suffix else ''
        street_postdir = street_postdir if street_postdir else ''

        # get address tags associated with street address
        mapped_tags = tag_map.get(street_address)
        tag_fields = [tag_field for tag_field in tag_fields if tag_field['traverse_links'] == 'true']
        for tag_field in tag_fields:
            found = False
            tag_key = tag_field['tag_key']
            # Look for tag in tag_map for street_address
            tag_value = None
            if mapped_tags:
                for mapped_tag in mapped_tags:
                    mapped_key = mapped_tag.get('key')
                # if street address has this tag already, continue to next tag_field
                    if mapped_key == tag_key:
                        found = True
                        break
            else:
                continue
            if found: # already have tag, go to next
                continue
            # Get set of linked addresses from address tags
            linked_addresses = set([(tag['linked_address'], tag['linked_path']) for tag in mapped_tags])
            if not linked_addresses:
                continue
            # Loop through linked address links looking for relationship = 'has_base'
            for linked_address, linked_path in linked_addresses:
                if linked_address == None:
                    continue
                if found:
                    break
                links = link_map.get(linked_address)
                if not links:
                    continue
                for link in links:
                    if found:
                        break
                    if link.get('relationship') == 'has base':
                        l_street_address = link['address_1']
                        parsed = parser.parse(l_street_address)
                        if all(a in geocode_map for a in (l_street_address, linked_address)):
                            # if both parcel geocodes have different geoms don't use:
                            if (geocode_map[l_street_address]['pwd'] is not None and geocode_map[l_street_address]['pwd'] !=
                                geocode_map[linked_address]['pwd']) and \
                                    (geocode_map[l_street_address]['dor'] is not None and geocode_map[l_street_address]['dor'] !=
                                        geocode_map[linked_address]['dor']):
                                if linked_address not in rejected_link_map:
                                    rejected_link_map[linked_address] = []
                                rejected_link_map[linked_address].append(l_street_address)
                                continue

                        l_low_num = parsed['components']['address']['low_num']
                        l_high_num = parsed['components']['address']['high_num_full']
                        l_street_full = parsed['components']['street']['full']
                        l_unit_type = parsed['components']['address_unit']['unit_type']
                        l_unit_num = parsed['components']['address_unit']['unit_num']
                        l_street_name = parsed['components']['street']['name']
                        l_street_predir = parsed['components']['street']['predir']
                        l_street_suffix = parsed['components']['street']['suffix']
                        l_street_postdir = parsed['components']['street']['postdir']
                        l_low_num = l_low_num if l_low_num else ''
                        l_street_full = l_street_full if l_street_full else ''
                        l_unit_type = l_unit_type if l_unit_type else ''
                        l_unit_num = l_unit_num if l_unit_num else ''
                        l_street_name = l_street_name if l_street_name else ''
                        l_street_predir = l_street_predir if l_street_predir else ''
                        l_street_suffix = l_street_suffix if l_street_suffix else ''
                        l_street_postdir = l_street_postdir if l_street_postdir else ''

                        # Condition for -- has base in range unit child -- search:
                        if l_low_num == low_num and l_street_predir == street_predir and l_street_name == street_name \
                            and l_street_suffix == street_suffix and l_street_postdir == street_postdir \
                                and l_unit_type == unit_type and l_unit_num == unit_num:
                            # Search tag map for this address and see if it has the missing key
                            link_tags = tag_map.get(link['address_1'])
                            for link_tag in link_tags:
                                mapped_key = link_tag['key']
                                # if street address has this tag already, continue to next tag_field
                                if mapped_key == tag_key:
                                    tag_value = link_tag['value']
                                    #linked_path = link_tag['linked_path'] if link_tag['linked_path'] else linked_address
                                    linked_address = link['address_1']
                                    linked_path = linked_path + ' unit child ' + linked_address
                                    add_tag_dict = {'street_address': street_address, 'key': tag_key,
                                                    'value': tag_value,
                                                    'linked_address': linked_address, 'linked_path': linked_path}
                                    new_linked_tags.append(add_tag_dict)
                                    found = True
                                    break

    """WRITE OUT"""

    if WRITE_OUT and len(new_linked_tags) > 0:
        print('Writing ', len(new_linked_tags), ' linked tags to address_tag table...')
        address_tag_table.write(new_linked_tags, chunk_size=150000)

    cleanup(address_file)
    
    transpired = datetime.now() - start
    print("Finished in ", transpired, " minutes.")
