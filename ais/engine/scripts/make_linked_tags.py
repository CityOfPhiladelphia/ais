from datetime import datetime
import datum
from ais import app

WRITE_OUT = True

start = datetime.now()
print('Starting at ', start)

config = app.config
db = datum.connect(config['DATABASES']['engine'])
address_table = db['address']
address_tag_table = db['address_tag']
source_address_table = db['source_address']
address_link_table = db['address_link']
tag_fields = config['ADDRESS_SUMMARY']['tag_fields']

print('Reading address links...')
link_map = {}
link_rows = address_link_table.read()
for link_row in link_rows:
    address_1 = link_row['address_1']
    address_2 = link_row['address_2']
    relationship = link_row['relationship']
    if not address_1 in link_map:
        link_map[address_1] = []
    link_map[address_1].append(link_row)

# define traversal order
traversal_order = ['has generic unit', 'matches unit', 'has base', 'overlaps', 'in range']

print('Reading address tags...')
tag_map = {}
tag_rows = address_tag_table.read()
for tag_row in tag_rows:
    street_address = tag_row['street_address']
    if not street_address in tag_map:
        tag_map[street_address] = []
    tag_map[street_address].append(tag_row)

err_map = {}

print('Reading addresses...')
address_rows = address_table.read()
print('Making linked tags...')
linked_tags_map = []
new_linked_tags = []
i = 1
done = False

while not done:

    print("Linked tags iteration: ", i)

    # add new tags to tag map
    for new_tag_row in new_linked_tags:
        street_address = new_tag_row['street_address']
        if not street_address in tag_map:
            tag_map[street_address] = []
        tag_map[street_address].append(new_tag_row)

    new_linked_tags = []
    # loop through addresses
    for address_row in address_rows:
        street_address = address_row['street_address']
        # get address tags associated with street address
        mapped_tags = tag_map.get(street_address)
        links = link_map.get(street_address)
        # sort links by traversal order
        sorted_links = []
        # sorted_links = [sorted_links.append(x) for x in links if x['relationship'] == rel for rel in traversal_order]
        if links:
            for rel in traversal_order:
                for link in links:
                    if link['relationship'] == rel:
                        sorted_links.append(link)
                        #links.remove(link)
        # loop through tag fields in config
        for tag_field in tag_fields:
            found = False
            # Skip tag_fields where 'traverse_links' value is false
            if tag_field['traverse_links'] != 'true':
                continue
            tag_key = tag_field['tag_key']
            # Look for tag in tag_map for street_address
            tag_value = None
            # if mapped_tags and not found: # Should always be not found at this point
            if mapped_tags:
                for mapped_tag in mapped_tags:
                    mapped_key = mapped_tag.get('key')
                   # if street address has this tag already, continue to next tag_field
                    if mapped_key != tag_key:
                        continue;
                    # TODO: handle empty string tag values as null and look for content from address_links
                    tag_value = mapped_tag['value']
                    found = True
                    break
            # Otherwise, look for tag in address links
            if not links or found:
                # Do something if tag can't be found by traversing links so API doesn't look for it
                continue
            # loop through links
            for slink in sorted_links:
                if found == True:
                    break
                link_address = slink.get('address_2')
                # get tags for current link
                link_tags = tag_map.get(link_address)
                if link_tags:
                    # loop through tags, looking for current tag
                    for tag in link_tags:
                        # if found, get value, linked address and linked path
                        # TODO: handle empty string tag values as null and keep looking for content from remaining address_links
                        if tag['key'] == tag_key:
                            tag_value = tag['value']
                            link_path = slink['relationship']
                            add_tag_dict = {'street_address': street_address, 'key': tag_key, 'value': tag_value,
                                            'linked_address': link_address, 'linked_path': link_path}
                            new_linked_tags.append(add_tag_dict)
                            found = True
                            break
                            # Do something if tag can't be found by traversing links so API doesn't look for it
    if len(new_linked_tags) > 0:
        linked_tags_map = linked_tags_map + new_linked_tags
    else:
        done = 'done'
    i += 1


"""WRITE OUT"""

if WRITE_OUT:
    print('Writing ', len(linked_tags_map), ' linked tags to address_tag table...')
    address_tag_table.write(linked_tags_map, chunk_size=150000)

print("Cleaning up...")
del link_rows
del tag_rows
del address_rows
del link_map
del tag_map
del linked_tags_map

transpired = datetime.now() - start
print("Finished in ", transpired, " minutes.")
