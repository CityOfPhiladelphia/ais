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
    key = tag_row['key']
    value = tag_row['value']
    if not street_address in tag_map:
        tag_map[street_address] = []
    tag_map[street_address].append(tag_row)

err_map = {}

print('Reading addresses...')
address_rows = address_table.read()
print('Making linked tags...')
linked_tags_map = []
# loop through addresses
for address_row in address_rows:
    street_address = address_row['street_address']
    writeout = True if street_address in ('921-29 E LYCOMING ST', '921-39 E LYCOMING ST', '920-28 LYCOMING ST') else False
    # get address tags associated with street address
    mapped_tags = tag_map.get(street_address)
    if writeout:
        print(mapped_tags)
    links = link_map.get(street_address)
    # sort links by traversal order
    sorted_links = []
    # sorted_links = [sorted_links.append(x) for x in links if x['relationship'] == rel for rel in traversal_order]
    if links:
        for rel in traversal_order:
            for link in links:
                if link['relationship'] == rel:
                    sorted_links.append(link)
                    links.remove(link)
        if writeout:
            print("Sorted links: ", street_address, sorted_links)
    else:
        if writeout:
            print('************** ', street_address, " has no links to search.")


    # loop through tag fields in config
    for tag_field in tag_fields:

        # Skip tag_fields where 'traverse_links' value is false
        if tag_field['traverse_links'] != 'true':
            continue

        tag_key = tag_field['tag_key']
        look = True
        search_tag_report = None
        found_tag_report = None

        if writeout:
            print("tag_key------------- ", tag_key)

        #try:
        #-------------------------------------------------------
        # Look for tag in tag_map for street_address
        tag_value = None
        if mapped_tags and look == True:
            if writeout:
                print(mapped_tags)
            for mapped_tag in mapped_tags:
                mapped_key = mapped_tag.get('key')
                if writeout:
                    print("mapped_key------------- ", mapped_key)
                if mapped_key != tag_key:
                    if writeout:
                        print("mapped_key != tag_key")
                    continue;
                tag_value = mapped_tag['value']# if tag and tag.get('key') == tag_key else None
                # if writeout:
                #     print(street_address, tag_key, tag_value)
                # if street address has this tag already, continue to next tag_field
                if tag_value and tag_value != '':
                    if writeout:
                        print(street_address, "already has tag ", mapped_tag, tag_value)
                    # move on to next tag field
                    #print(street_address, tag_key, tag_value)
                    look = False
                    break
                else:
                    if writeout:
                        print("didn't break: ", tag_value)
        #--------------------------------------------------------
        # Otherwise, look for tag in address links
        #print("Searching links for tag: ", street_address, tag_key)
        if not links or look == False:
            # Do something if tag can't be found by traversing links so API doesn't look for it
            #print(street_address, " has no links.")
            continue
        # loop through links
        found = False
        for link in sorted_links:
            if found == True:
                break
                #print(link)
            link_address = link.get('address_2')
            # get tags for current link
            link_tags = tag_map.get(link_address)
            if link_tags:
                # loop through tags, looking for current tag
                for tag in link_tags:
                    #print(tag)
                    # if found, get value, linked address and linked path
                    if tag['key'] == tag_key:
                        if writeout:
                            print(street_address, " found tag for ", tag_key, "from ", link_address)
                        #tag_id = tag['id']
                        tag_value = tag['value']
                        if tag_value and tag_value != '':
                            link_path = link['relationship']
                            add_tag_dict = {'street_address': street_address, 'key': tag_key, 'value': tag_value, 'linked_address': link_address, 'linked_path': link_path}
                            linked_tags_map.append(add_tag_dict)
                            found_tag_report = [{key: value} for key, value in add_tag_dict.items()]
                            #print(found_tag_report)
                            if writeout:
                                print(found_tag_report)
                            found = True
                            break
                            #raise
                        # Do something if tag can't be found by traversing links so API doesn't look for it
        # except:
        #     print(street_address)
        #     print(search_tag_report)
        #     print(found_tag_report)
        #     continue


"""WRITE OUT"""

if WRITE_OUT:
    print('Writing ', len(linked_tags_map), ' linked tags to address_tag table...')
    address_tag_table.write(linked_tags_map, chunk_size=150000)

    # for id, linked_vals in linked_tags_map.items():
    #     linked_address = linked_vals['linked_address']
    #     linked_path = linked_vals['linked_path']
    #     linked_tag_stmt = '''
    #         update address_tag
    # 	    set linked_address = '{linked_address}',
    # 	        linked_path = '{linked_path}'
    # 		where address_tag.id = {id}
    #     '''.format(linked_address=linked_address, linked_path=linked_path, id=id)
    #
    #     db.execute(linked_tag_stmt)
    #     db.save()

transpired = datetime.now() - start

print("Cleaning up...")
del link_rows
del tag_rows
del address_rows
del link_map
del tag_map
del linked_tags_map


print("Finished in ", transpired, " minutes.")