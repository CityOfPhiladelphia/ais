import sys
from datetime import datetime
from shapely.wkt import loads
from datetime import datetime
from copy import deepcopy
import datum
from ais import app
from ais.models import Address
# DEV
import traceback
from pprint import pprint

print('Starting...')
start = datetime.now()

# TODO: This should probably make a DB query for each address, rather than chunking
# into street names. Getting hard to manage.

"""SET UP"""

config = app.config
db = datum.connect(config['DATABASES']['engine'])
tag_fields = config['ADDRESS_SUMMARY']['tag_fields']
non_summary_tags = config['ADDRESS_SUMMARY']['non_summary_tags']
geocode_table = db['geocode']
address_table = db['address']
max_values = config['ADDRESS_SUMMARY']['max_values']
geocode_types = config['ADDRESS_SUMMARY']['geocode_types']
geocode_priority_map = config['ADDRESS_SUMMARY']['geocode_priority']
#geocode_types_on_curb = config['ADDRESS_SUMMARY']['geocode_types_on_curb']
geocode_types_in_street = config['ADDRESS_SUMMARY']['geocode_types_in_street']

tag_table = db['address_tag']
link_table = db['address_link']
address_summary_table = db['address_summary']

# DEV
WRITE_OUT = True


def wkt_to_xy(wkt):
    xy = wkt.replace('POINT(', '')
    xy = xy.replace(')', '')
    split = xy.split(' ')
    return float(split[0]), float(split[1])


print('Reading address links...')
link_map = {}
link_rows = link_table.read()
for link_row in link_rows:
    address_1 = link_row['address_1']
    address_2 = link_row['address_2']
    relationship = link_row['relationship']
    if not address_1 in link_map:
        link_map[address_1] = []
    link_map[address_1].append(link_row)


def get_tag_by_key(tag_rows, search_key):
    for tag_row in tag_rows:
        if tag_row['key'] == search_key:
            return tag_row['value']
    return None


# Get street names for chunking addresses
print('Reading street names...')
street_name_stmt = '''
	select distinct street_name from address order by street_name
'''
street_names = [x['street_name'] for x in db.execute(street_name_stmt)]

if WRITE_OUT:
    print('Dropping indexes...')
    address_summary_table.drop_index('street_address')
    trgm_idx_stmt = '''
	DROP INDEX IF EXISTS address_summary_opa_owners_trigram_idx;
	'''
    db.execute(trgm_idx_stmt)
    db.save()

    print('Deleting existing summary rows...')
    address_summary_table.delete()

    print('Creating temporary street name index...')
    address_table.create_index('street_name')

print('Reading XYs...')
geocode_rows = geocode_table.read( \
    fields=['street_address', 'geocode_type'], \
    geom_field='geom' \
    )
geocode_map = {}  # street_address => [geocode rows]
for geocode_row in geocode_rows:
    street_address = geocode_row['street_address']
    geocode_type_str = (list(geocode_priority_map.keys())[list(geocode_priority_map.values()).index(geocode_row['geocode_type'])])
    geocode_row['geocode_type'] = geocode_type_str
    if not street_address in geocode_map:
        geocode_map[street_address] = []
    geocode_map[street_address].append(geocode_row)

print('Indexing addresses...')
address_rows_all = address_table.read()
street_map = {}  # street_name => [address rows]
for address_row in address_rows_all:
    street_name = address_row['street_name']
    if not street_name in street_map:
        street_map[street_name] = []
    street_map[street_name].append(address_row)

address_map = {x['street_address']: x for x in address_rows_all}

print('Reading unit children...')
unit_child_stmt = '''
	select address_1, address_2
	from address_link
	where relationship = 'has generic unit'
'''
unit_child_rows = db.execute(unit_child_stmt)
unit_child_map = {}  # unit parent => [unit children]
unit_children_set = set()  # use this to lookup children quickly

for unit_child_row in unit_child_rows:
    child_address = unit_child_row['address_1']
    parent_address = unit_child_row['address_2']
    unit_child_map.setdefault(parent_address, [])
    unit_child_map[parent_address].append(child_address)
    unit_children_set.add(child_address)

# Make a map of generic ("pound") unit addresses and corresponding tags for
# all child unit addreses (APT, UNIT). This is to consolidate redundant addrs
# like 1 CHESTNUT ST UNIT 1, 1 CHESTNUT # 1. Default to pounds.
generic_unit_tags = {}  # pound address => {tag key: [tag vals]}

summary_rows = []
geocode_errors = 0

"""MAIN"""

cur_first_character = None

print('Reading addresses...')
for i, street_name in enumerate(street_names):
    first_character = street_name[0]
    if first_character != cur_first_character:
        print(street_name)
        cur_first_character = first_character

    address_rows = street_map[street_name]

    # Get address tags
    tag_map = {}  # street_address => tag_key => [tag values]
    tag_keys = [x['tag_key'] for x in tag_fields]
    tag_where = "key in ({})".format(', '.join(["'{}'".format(x) for x in tag_keys]))
    tag_stmt = '''
		select street_address, key, value from address_tag
		where street_address in (
			select street_address from address where street_name = '{}'
		)
	'''.format(street_name)
    tag_rows = db.execute(tag_stmt)

    # Make tag map
    for tag_row in tag_rows:
        street_address = tag_row['street_address']
        if not street_address in tag_map:
            tag_map[street_address] = []
        # tag_map_obj = {tag_row['key']: tag_row['value']}
        tag_map[street_address].append(tag_row)

    for i, address_row in enumerate(address_rows):
        street_address = address_row['street_address']

        # Skip unit children
        if street_address in unit_children_set:
            continue

        summary_row = deepcopy(address_row)
        tag_rows = tag_map.get(street_address)

        # If this address has unit children, append those tags
        if street_address in unit_child_map:
            unit_children = unit_child_map[street_address]
            for unit_child in unit_children:
                if unit_child in tag_map and tag_rows is not None:
                    tag_rows += tag_map[unit_child]

        '''
        GET TAG FIELDS
        '''

        for tag_field in tag_fields:
            field_name = tag_field['name']
            if field_name in non_summary_tags:
                continue
            tag_key = tag_field['tag_key']
            field_type = tag_field['type']
            values = []

            # If the address has tags at all
            if tag_rows:
                # Loop trying to find
                for tag_row in tag_rows:
                    if tag_row['key'] == tag_key:
                        # Make uppercase
                        value = tag_row['value'].upper()
                        values.append(value)

            # if parent_unit_address:
            # 	generic_unit_tags.setdefault(parent_unit_address, {})
            # 	generic_unit_tags[parent_unit_address].setdefault(field_name, [])

            # 	if len(values) > 0:
            # 		generic_unit_tags[parent_unit_address][field_name] += values
            # 	else:
            # 		if field_type == 'number':
            # 			generic_unit_tags[parent_unit_address][field_name].append(None)
            # 		else:
            # 			generic_unit_tags[parent_unit_address][field_name].append('')
            # else:

            # values = list(set(values)) # only use distinct values
            values = list(set(filter(None, values)))
            if len(values) > 0:
                # Hack to supersede generic unit parser tags over base address parser tags
                # TODO: handle in Passyunk / standardize '#' unit_types to generic type (APT or UNIT) / fix source addresses
                if 'usps' in tag_key:
                    value_address_map = {}
                    generic_usps_value = ''
                    for tag_row in tag_rows:
                        if tag_row['key'] == tag_key:
                            tag_address = tag_row['street_address']
                            if tag_address not in value_address_map:
                                value_address_map[tag_address] = [] #make list just in case there's more than one generic unit address with a unique value
                            value = tag_row['value'].upper()
                            value_address_map[tag_address].append(value)
                    for address in value_address_map:
                        if '#' not in address:
                            value = value_address_map[address][0] # arbitrarily choose first value
                        else:
                            generic_usps_value = value_address_map[address][0] # arbitrarily choose first value
                    value = value if value else generic_usps_value
                else:
                    value = '|'.join(values[:max_values])
            else:
                if field_type == 'number':
                    value = None
                else:
                    value = ''

            summary_row[field_name] = value
        # print('{} => {}'.format(field_name, value))

        # Geocode
        geocode_rows = geocode_map.get(street_address, [])
        if len(geocode_rows) == 0: geocode_errors += 1

        xy_map = {x['geocode_type']: x['geom'] for x in geocode_rows}
        geocode_vals = None
        # Geocode parcel xys
        for geocode_type in geocode_types:
            if geocode_type in xy_map:
                xy_wkt = xy_map[geocode_type]
                x, y = wkt_to_xy(xy_wkt)

                geocode_vals = {
                    'geocode_type': geocode_type,
                    'geocode_x': x,
                    'geocode_y': y,
                    'geocode_street_x': None,
                    'geocode_street_y': None,
                }
                break
        # Geocode parcel xys in street (same geocode_type as parcel xy)
        for geocode_type in geocode_types_in_street:
            if geocode_type in xy_map:
                xy_wkt = xy_map[geocode_type]
                x, y = wkt_to_xy(xy_wkt)
                #TODO: Resolve this quickfix
                try:
                    geocode_vals['geocode_street_x'] = x
                    geocode_vals['geocode_street_y'] = y
                except:
                    print("Could not get geocode_street values for: ", street_address)

                break

        # Only write out addresses with an XY
        if geocode_vals:
            summary_row.update(geocode_vals)
            summary_rows.append(summary_row)

"""WRITE OUT"""

if WRITE_OUT:
    print('Writing summary rows...')
    address_summary_table.write(summary_rows, chunk_size=100000)
    del summary_rows

    print('Creating indexes...')
    address_summary_table.create_index('street_address')

    index_stmt = '''
		CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE INDEX address_summary_opa_owners_trigram_idx ON address_summary USING GIN (opa_owners gin_trgm_ops);
	'''
    db.execute(index_stmt)
    db.save()

    print('Deleting temporary street name index...')
    address_summary_table.drop_index('street_name')

    print('Populating seg IDs...')
    seg_stmt = '''
		update address_summary asm
		set seg_id = ast.seg_id, seg_side = ast.seg_side
		from address_street ast
		where ast.street_address = asm.street_address
    '''
    db.execute(seg_stmt)
    db.save()

    print('Populating street codes...')
    stcode_stmt = '''
	    update address_summary asm
	    set street_code = sts.street_code
		from street_segment sts
		where sts.seg_id = asm.seg_id
    '''
    db.execute(stcode_stmt)
    db.save()

    # Update street codes for ranged addresses with overlapping street segs
    rstcode_stmt = '''
        with scnulls as (
        select street_address, address_low, address_low_suffix, address_low_frac, street_predir, street_name, street_suffix, street_postdir
        from address_summary asm 
        where street_code is null and address_high is not null
        )
        update address_summary asm
        set street_code = final.street_code
        from
        (
        select asm.street_address, asmj.street_code 
        from scnulls asm
        inner join address_summary asmj on asmj.street_code is not null and asmj.address_low = asm.address_low and asmj.address_low_suffix = asm.address_low_suffix and asmj.address_low_frac = asm.address_low_frac
        and asm.street_predir = asmj.street_predir and asm.street_name = asmj.street_name and asmj.street_suffix = asm.street_suffix and asmj.street_postdir = asm.street_postdir
        group by asm.street_address, asmj.street_code
        )final
        where final.street_address = asm.street_address    
    '''
    db.execute(rstcode_stmt)
    db.save()

    # print('Populating PWD parcel IDs...')
    # parcel_stmt = '''
    # 	update address_summary asm
    # 	set pwd_parcel_id = p.parcel_id
    # 	from
    # 		address_parcel ap,
    # 		pwd_parcel p
    # 	where
    # 		ap.parcel_source = 'pwd' and
    # 		ap.match_type != 'spatial' and
    # 		ap.street_address = asm.street_address and
    # 		p.id = ap.parcel_row_id
    # '''
    # db.execute(parcel_stmt)
    # db.save()
    #
    # print('Populating DOR parcel IDs...')
    # parcel_stmt = '''
    # 	update address_summary asm
    # 	set dor_parcel_id = d.parcel_id
    # 	from
    # 		address_parcel ap,
    # 		dor_parcel d
    # 	where
    # 		ap.parcel_source = 'dor' and
    # 		ap.match_type != 'spatial' and
    # 		ap.street_address = asm.street_address and
    # 		d.id = ap.parcel_row_id
    # '''
    # db.execute(parcel_stmt)
    # db.save()
    #
    print('Populating OPA accounts...')
    prop_stmt = '''
    	update address_summary asm
    	set opa_account_num = op.account_num,
    		opa_owners = op.owners,
    		opa_address = op.street_address
    	from address_property ap, opa_property op
    	where asm.street_address = ap.street_address and
    		ap.opa_account_num = op.account_num
    '''
    db.execute(prop_stmt)
    db.save()

    print('Populating li_parcel_id')
    li_pin_stmt = '''
        update address_summary asm
        set li_parcel_id = 
            case
                when pwd_parcel_id != '' then pwd_parcel_id
                when bin_parcel_id != '' then bin_parcel_id 
		when opa_account_num != '' then '-' || opa_account_num
		else ''
	    end
    '''
    db.execute(li_pin_stmt)
    db.save()

# This is depreciated in favor of Zip Codes/Zip4s read from Passyunk Components (address_tag table)
# print('Populating ZIP codes...')
# zip_stmt = '''
# 	update address_summary asm
# 	set zip_code = zr.zip_code,
# 		zip_4 =
# 			case when az.match_type = 'ignore_unit' then ''
# 				else zr.zip_4 end
# 	from address_zip az, zip_range zr
# 	where asm.street_address = az.street_address and
# 		az.usps_id = zr.usps_id
# '''.format(address_summary_table)
# db.execute(zip_stmt)
# db.save()

db.close()
print('{} geocode errors'.format(geocode_errors))
print('Finished in {} seconds'.format(datetime.now() - start))
