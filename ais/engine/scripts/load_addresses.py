import sys
import os
import csv
from copy import deepcopy
from datetime import datetime
import datum
from ais import app
from ais.models import Address
from ais.util import parity_for_num, parity_for_range
# DEV
import traceback
from pprint import pprint


print('Starting...')
start = datetime.now()

config = app.config
Parser = config['PARSER']

sources = config['ADDRESS_SOURCES']
db = datum.connect(config['DATABASES']['engine'])
address_table = db['address']
address_tag_table = db['address_tag']
source_address_table = db['source_address']
address_link_table = db['address_link']
street_segment_table = db['street_segment']
address_street_table = db['address_street']
true_range_view_name = 'true_range'
# TODO: something more elegant here.
true_range_select_stmt = '''
    select
         coalesce(r.seg_id, l.seg_id) as seg_id,
         r.low as true_right_from,
         r.high as true_right_to,
         l.low as true_left_from,
         l.high as true_left_to
    from (select
              asr.seg_id,
              min(a.address_low) as low,
              greatest(max(a.address_low), max(a.address_high)) as high
         from address a join address_street asr on a.street_address = asr.street_address
         group by asr.seg_id, asr.seg_side
         having asr.seg_id is not null and asr.seg_side = 'R') r
    full outer join
         (select
              asl.seg_id,
              min(a.address_low) as low,
              greatest(max(a.address_low), max(a.address_high)) as high
         from address a join address_street asl on a.street_address = asl.street_address
         group by asl.seg_id, asl.seg_side
         having asl.seg_id is not null and asl.seg_side = 'L') l
    on r.seg_id = l.seg_id
    order by r.seg_id
'''
parcel_layers = config['BASE_DATA_SOURCES']['parcels']
address_parcel_table = db['address_parcel']
address_property_table = db['address_property']
address_error_table = db['address_error']
WRITE_OUT = True

DEV = False  # This will target a single address
DEV_ADDRESS = '119-23 1/2 CATHARINE ST # A'
DEV_ADDRESS_COMPS = {
    'address_low':      '119',
    # 'address_high':     952,
    'street_name':      "'CATHARINE'",
    'street_suffix':    "'ST'",
}
DEV_STREET_NAME = 'CATHARINE'

# Logging stuff.
address_errors = []
# Use these maps to write out one error per source address/source name pair.
source_map = {}  # source_address => [source_names]
source_address_map = {}  # street_address => [source_addresses]


"""MAIN"""

addresses = []
street_addresses_seen = set()
address_tags = []
address_tag_strings = set()  # Pipe-joined addr/key/value triples
source_addresses = []
links = []  # dicts of address, relationship, address triples

if WRITE_OUT:
    print('Dropping indexes...')
    for table in (address_table, address_tag_table, source_address_table):
        table.drop_index('street_address')
    address_link_table.drop_index('address_1')
    address_link_table.drop_index('address_2')

    print('Deleting existing addresses...')
    address_table.delete()
    print('Deleting existing address tags...')
    address_tag_table.delete()
    print('Deleting existing source addresses...')
    source_address_table.delete()
    print('Deleting existing address links...')
    address_link_table.delete()
    print('Deleting address errors...')
    address_error_table.delete()

# Loop over address sources
for source in sources:
    source_name = source['name']

    # Determine address field mapping: single or comps
    address_fields = source['address_fields']
    # Invert for aliases arg on read()
    aliases = {value: key for key, value in address_fields.items()}
    if len(address_fields) == 1:
        if 'street_address' in address_fields:
            source_type = 'single_field'
        else: raise ValueError('Unknown address field mapping')
        preprocessor = source.get('preprocessor')
    else:
        source_type = 'comps'
        # Check for necessary components
        for field_name in ['address_low', 'street_name']:
            if not field_name in address_fields:
                raise ValueError('Missing required address field: {}'\
                    .format(field_name))
        if 'preprocessor' not in source:
            raise ValueError('No preprocessor specified for address source \
                `{}`'.format(source_name))
        preprocessor = source['preprocessor']

    # Get other params
    address_fields = source['address_fields']
    source_fields = list(address_fields.values())
    if 'tag_fields' in source:
        source_fields += [x['source_field'] for x in source['tag_fields']]
    source_db_name = source['db']
    source_db = datum.connect(config['DATABASES'][source_db_name])
    source_table = source_db[source['table']]
    print('Reading from {}...'.format(source_name))

    # Add source fields depending on address type
    # Not using this since we implemented the `aliases` arg on .read()
    # if source_type == 'single_field':
        # source_fields.append('{} AS street_address'\
        #     .format(address_fields['street_address']))
        # source_fields.append(address_fields['street_address'])
    # elif source_type == 'comps':
        # for address_field_std, address_field in address_fields.items():
        #     source_fields.append('{} AS {}'\
        #         .format(address_field, address_field_std))
        # source_fields.append(address_fields.values())

    where = source['where'] if 'where' in source else None

    # For debugging. (Only fetch a specific address.)
    if DEV:
        if source_type == 'single_field':
            dev_where = "{} = '{}'"\
                .format(address_fields['street_address'], DEV_ADDRESS)
        elif source_type == 'comps':
            clauses = ["{} = {}".format(address_fields[key], value) \
                for key, value in DEV_ADDRESS_COMPS.items()]
            dev_where = ' AND '.join(clauses)
        if where:
                where += ' AND ' + dev_where
        else: where = dev_where
        source_rows = source_table.read(fields=source_fields, \
            aliases=aliases, where=where)
    else:
        if source_type == 'single_field':
            source_rows = source_table.read(fields=source_fields, \
                aliases=aliases, where=where)
        elif source_type == 'comps':
            source_rows = source_table.read(fields=source_fields, \
                aliases=aliases, where=where)

    # Loop over addresses
    for i, source_row in enumerate(source_rows):
        if i % 100000 == 0:
            print(i)

        # Get source address and add source to map. We do this outside the
        # try statement so that source_address is always properly set for
        # logging errors.
        # if source_type == 'single_field':
        #     source_address = source_row['street_address']
        # else:
        #     source_address = preprocessor(source_row)

        # If there's a preprocessor, apply. This could be single field or comps.
        if preprocessor:
            source_address = preprocessor(source_row)
        # Must be a single field
        else:
            source_address = source_row['street_address']
        
        if source_address is None:
            # TODO: it might be helpful to log this, but right now we aren't
            # logging object IDs so there would be no way to identify the 
            # null address in the source dataset. Just skipping for now.
            continue

        source_map.setdefault(source_address, []).append(source_name)

        # Make sure this is reset on each run (also for logging)
        street_address = None

        try:
            # Try parsing
            try:
                address = Address(source_address)
            except:
                raise ValueError('Could not parse')

            # Get street address and map to source address
            street_address = address.street_address
            _source_addresses = source_address_map.setdefault(street_address, [])
            if not source_address in _source_addresses:
                _source_addresses.append(source_address)

            # Check for zero address
            if address.address_low == 0:
                raise ValueError('Low number is zero')

            # Add address
            if not street_address in street_addresses_seen:
                addresses.append(address)
                street_addresses_seen.add(street_address)

            # Make source address
            source_address_dict = {
                'source_name':      source_name,
                'source_address':   source_address,
                'street_address':   street_address,
            }
            source_addresses.append(source_address_dict)

            # Make address tags
            for tag_field in source.get('tag_fields', []):
                source_field = tag_field['source_field']
                value = source_row[source_field]

                # Skip empty tags
                if value is None or len(str(value).strip()) == 0:
                    continue

                # Make uppercase
                if isinstance(value, str):
                    value = value.upper()

                key = tag_field['key']
                value = source_row[source_field]

                # Make address tag string to check if we already added this tag
                address_tag_string_vals = [
                    street_address,
                    key,
                    value,
                ]
                address_tag_string = '|'.join([str(x) for x in \
                    address_tag_string_vals])

                if not address_tag_string in address_tag_strings:
                    address_tag = {
                        'street_address':   street_address,
                        'key':              tag_field['key'],
                        'value':            source_row[source_field]
                    }
                    address_tags.append(address_tag)
                    address_tag_strings.add(address_tag_string)

            # If it's a unit or low num suffix, make sure we have the base
            # address
            if not address.is_base:
                base_address = address.base_address
                if not base_address in street_addresses_seen:
                    base_address_obj = Address(base_address)
                    addresses.append(base_address_obj)
                    street_addresses_seen.add(base_address)

                    # Add to source address map
                    _source_addresses = source_address_map.setdefault(base_address, [])
                    if not source_address in _source_addresses:
                        _source_addresses.append(source_address)

            # If it's a range, make sure we have all the child addresses
            for child_obj in address.child_addresses:
                child_street_address = child_obj.street_address
                if not child_street_address in street_addresses_seen:
                    addresses.append(child_obj)
                    street_addresses_seen.add(child_street_address)

                    # Add to source address map
                    _source_addresses = source_address_map.setdefault(child_street_address, [])
                    if not source_address in _source_addresses:
                        _source_addresses.append(source_address)

        except ValueError as e:
            address_error = {
                'source_name':      source_name,
                'source_address':   source_address,
                'street_address':   street_address or '',
                'level':            'error',
                'reason':           str(e),
                # TODO: haven't needed these so far, but they should be passed
                # in with the exception if we ever do.
                'notes':            '',
            }
            address_errors.append(address_error)

    if WRITE_OUT:
        print('Writing {} address tags...'.format(len(address_tags)))
        address_tag_table.write(address_tags, chunk_size=150000)
        address_tags = []
        address_tag_strings = set()

        print('Writing {} source addresses...'.format(len(source_addresses)))
        source_address_table.write(source_addresses, chunk_size=150000)
        source_addresses = []

    source_db.close()

if WRITE_OUT:
    print('Writing {} addresses...'.format(len(addresses)))
    insert_rows = [dict(x) for x in addresses]
    address_table.write(insert_rows, chunk_size=150000)
    del insert_rows


###############################################################################
# ADDRESS LINKS
###############################################################################

print('\n** ADDRESS LINKS **')
print('Indexing addresses...')
street_address_map = {}     # street_full => [addresses]
street_range_map = {}       # street_full => [range addresses]
base_address_map = {}       # base_address => [unit addresses]

for i, address in enumerate(addresses):
    if i % 100000 == 0:
        print(i)

    street_full = address.street_full
    if not street_full in street_address_map:
        street_address_map[street_full] = []
        street_range_map[street_full] = []
    street_address_map[street_full].append(address)

    if address.address_high is not None and address.unit_type is None:
        street_range_map[street_full].append(address)

    base_address = address.base_address
    if address.unit_type is not None:
        if not base_address in base_address_map:
            base_address_map[base_address] = []
        base_address_map[base_address].append(address)

# Loop over addresses
print('Making address links...')

generic_unit_types = set(['#', 'APT', 'UNIT'])
apt_unit_types = set(['APT', 'UNIT'])

for i, address in enumerate(addresses):
    if i % 100000 == 0:
        print(i)

    if address.unit_type is not None:
        # Base link
        base_link = {
            'address_1':        address.street_address,
            'relationship':     'has base',
            'address_2':        address.base_address,
        }
        links.append(base_link)

        # Sibling generic unit links
        # These relate unit addresses to all other addresses that share the same
        # generic unit. Bidirectional.
        if address.unit_type in generic_unit_types:
            base_address = address.base_address
            base_matches = base_address_map[base_address]
            for base_match in base_matches:
                if address.unit_num == base_match.unit_num and \
                    address.unit_type != base_match.unit_type and \
                    base_match.unit_type in generic_unit_types:
                    matches_unit_link_1 = {
                        'address_1':        address.street_address,
                        'relationship':     'matches unit',
                        'address_2':        base_match.street_address,
                    }
                    matches_unit_link_2 = {
                        'address_1':        base_match.street_address,
                        'relationship':     'matches unit',
                        'address_2':        address.street_address,
                    }
                    links.append(matches_unit_link_1)
                    links.append(matches_unit_link_2)

            # Parent generic unit link
            # ex. 902 PINE ST APT 2R => 902 PINE ST # 2R
            # We only want to create these if the generic (#) address was seen
            # in the data. Don't make like we make child addresses for ranges.
            if address.unit_type in apt_unit_types:
                generic_unit = address.generic_unit
                if generic_unit in street_addresses_seen:
                    parent_unit_link = {
                        'address_1':            address.street_address,
                        'relationship':         'has generic unit',
                        'address_2':            generic_unit,
                    }
                    links.append(parent_unit_link)

    # Child link
    elif address.address_high is None:
        address_low = address.address_low
        address_suffix = address.address_low_suffix
        parity = address.parity
        ranges_on_street = street_range_map[address.street_full]

        for range_on_street in ranges_on_street:
            if (range_on_street.address_low <= address_low <= \
                range_on_street.address_high) and \
                range_on_street.parity == parity and \
                range_on_street.address_low_suffix == address_suffix:
                child_link = {
                    'address_1':        address.street_address,
                    'relationship':     'in range',
                    'address_2':        range_on_street.street_address,
                }
                links.append(child_link)
                break

print('Writing address links...')
if WRITE_OUT:
    address_link_table.write(links, chunk_size=150000)
    print('Created {} address links'.format(len(links)))
del links


###############################################################################
# ADDRESS-STREETS
###############################################################################

print('\n** ADDRESS-STREETS **')

# SET UP LOGGING / QC
street_warning_map = {}  # street_address => [{reason, notes}]
street_error_map = {}  # # street_address => {reason, notes}

class ContinueIteration(Exception):
    pass

def had_street_warning(street_address, reason, notes=None):
    '''
    Convenience function to log street warnings as they happen.
    '''
    global street_warning_map
    address_warnings = street_warning_map.setdefault(street_address, [])
    warning = {
        'reason':   reason,
        'notes':    notes or '',
    }
    address_warnings.append(warning)

def had_street_error(street_address, reason, notes=None):
    '''
    This is a wrapper around had_street_warning that raises an error.
    Technically these are written out as warnings since they are non-fatal.
    '''
    global street_error_map
    street_error_map[street_address] = {'reason': reason, 'notes': notes}
    had_street_warning(street_address, reason, notes=notes)
    raise ContinueIteration

# START WORK
if WRITE_OUT:
    print('Deleting existing address-streets...')
    address_street_table.delete()

print('Reading street segments...')
seg_fields = [
    'seg_id',
    'street_full',
    'left_from',
    'left_to',
    'right_from',
    'right_to'
]
seg_map = {}
seg_rows = street_segment_table.read(fields=seg_fields)
for seg_row in seg_rows:
    street_full = seg_row['street_full']
    street_full_segs = seg_map.setdefault(street_full, [])
    street_full_segs.append(seg_row)

address_streets = []
base_address_map = {}  # base_address => {seg_id, seg_side, had_alias}

print('Making address-streets...')
for address in addresses:
    try:
        street_address = address.street_address
        base_address = address.base_address

        # If the base address already had an error, raise it again
        if base_address in street_error_map:
            error = street_error_map[base_address]
            reason = error['reason']
            notes = error['notes']
            had_street_error(street_address, reason, notes=notes)

        match = None
        had_alias = None

        # If we've already seen the base address before, used cached values
        if base_address in base_address_map:
            # Make match, also
            match = base_address_map[base_address]
            seg_id = match['seg_id']
            seg_side = match['seg_side']
            had_alias = match['had_alias']
            
            # If there were warnings, raise them again
            for warning in street_warning_map.get(base_address, []):
                had_street_warning(
                    warning['street_address'],
                    warning['reason'],
                    notes=warning.get('notes')
                )

        # Otherwise this is a new address
        else:
            # There are some types of warnings we only want to write out if a 
            # more serious error isn't raised first. Keep these here, append
            # during the seg loop, then call had_street_warning for each one
            # if we get to that point.
            deferred_warnings = []

            # Check for valid street
            address_low = address.address_low
            address_high = address.address_high
            street_full = address.street_full
            address_parity = address.parity
            if not street_full in seg_map:
                had_street_error(street_address, 'Not a valid street')

            matching_segs = seg_map[street_full]
            matching_seg = None
            matching_side = None

            # Loop through segs for that street full
            for seg in matching_segs:
                left_from = seg['left_from']
                left_to = seg['left_to']
                right_from = seg['right_from']
                right_to = seg['right_to']

                left_parity = parity_for_range(left_from, left_to)
                right_parity = parity_for_range(right_from, right_to)

                # Match to side of street based on parity
                check_from = None
                check_to = None

                if left_parity in [address_parity, 'B']:
                    check_from = left_from
                    check_to = left_to
                    matching_side = 'L'
                elif right_parity in [address_parity, 'B']:
                    check_from = right_from
                    check_to = right_to
                    matching_side = 'R'
                else:
                    continue
                
                # SINGLE ADDRESS
                if address_high is None:
                    if check_from <= address_low <= check_to:
                        matching_seg = seg
                        break

                # RANGE ADDRESS
                else:
                    # Check for a previously matched seg
                    if matching_seg:
                        seg_ids = sorted([x['seg_id'] for x in \
                            [matching_seg, seg]])
                        notes = ', '.join([str(x) for x in seg_ids])
                        had_street_error(street_address, 'Range address matches multiple street segments', notes=notes)

                    # If the low num is in range
                    if check_from <= address_low <= check_to:
                        # Match it
                        matching_seg = seg

                        # If the high num is out of range
                        if check_to < address_high:
                            # Warn
                            deferred_warnings.append({
                                'street_address': street_address,
                                'reason': 'High address out of range',
                                'notes': 'Seg {}: {} to {}'.format(
                                    matching_seg['seg_id'],
                                    check_from,
                                    check_to
                                )
                            })

                    # If only the high address is in range (unlikely)
                    elif check_from <= address_high <= check_to:
                        # Match and warn
                        matching_seg = seg
                        deferred_warnings.append({
                            'street_address': street_address,
                            'reason': 'Low address out of range',
                            'notes': 'Seg {}: {} to {}'.format(
                                matching_seg['seg_id'],
                                check_from,
                                check_to
                            )
                        })

            # Store the match
            if matching_seg:
                match = {
                    'seg_id':               matching_seg['seg_id'],
                    'seg_side':             matching_side,
                    'had_alias':            had_alias,
                }
                base_address_map[base_address] = match

            # Handle deferred warnings
            for warning in deferred_warnings:
                had_street_warning(
                    warning['street_address'],
                    warning['reason'],
                    notes=warning.get('notes')
                )

        if match is None:
            had_street_error(street_address, 'Out of street range')

        if had_alias:
            # TODO: check against aliases; raise warning if alias used
            pass

        seg_id = match['seg_id']
        seg_side = match['seg_side']

        address_street = {
            'street_address':   street_address,
            'seg_id':           seg_id,
            'seg_side':         seg_side,
        }
        address_streets.append(address_street)

    except ContinueIteration:
        pass

if WRITE_OUT:
    print('Writing address-streets...')
    address_street_table.write(address_streets, chunk_size=150000)
del address_streets

# Handle errors
for street_address, warnings in street_warning_map.items():
    for warning_dict in warnings:
        reason = warning_dict['reason']
        notes = warning_dict['notes']

        # Get source addresses
        # TEMP: put this in a try statement until some base address parsing
        # issues in Passyunk are resolved
        try:
            _source_addresses = source_address_map[street_address]
        except KeyError:
            continue

        for source_address in _source_addresses:
            # Get sources
            sources = source_map[source_address]
            for source in sources:
                address_errors.append({
                    'source_name':      source,
                    'source_address':   source_address,
                    'street_address':   street_address,
                    'level':            'warning',
                    'reason':           reason,
                    'notes':            notes,
                })


################################################################################
# ADDRESS-PARCELS
################################################################################

print('\n** ADDRESS-PARCELS **')

# This maps address variant names to AddressParcel match types
ADDRESS_VARIANT_MATCH_TYPE = {
    'base_address':             'base',
    'base_address_no_suffix':   'base_no_suffix',
    'generic_unit':             'generic_unit'
}

match_counts = {x: 0 for x in ADDRESS_VARIANT_MATCH_TYPE.values()}
match_counts['address_in_parcel_range'] = 0
match_counts['parcel_in_address_range'] = 0

address_parcels = []

if WRITE_OUT:
    print('Dropping index on address-parcels...')
    address_parcel_table.drop_index('street_address')
    print('Deleting existing address-parcels...')
    address_parcel_table.delete()

for parcel_layer in parcel_layers:
    source_table_name = parcel_layer + '_parcel'
    source_table = db[source_table_name]
    print('Reading from {}...'.format(parcel_layer))

    if DEV:
        where = "street_name = '{}'".format(DEV_STREET_NAME)
        parcel_rows = source_table.read(fields=['street_address', 'id'], \
            where=where)
    else:
        parcel_rows = source_table.read(fields=['street_address', 'id'])

    print('Building indexes...')
    # Index: street_address => [row_ids]
    parcel_map = {}
    # Index: street full => hundred block => 
    #   {row_id/address low/high/suffix dicts}
    block_map = {}

    for parcel_row in parcel_rows:
        street_address = parcel_row['street_address']
        row_id = parcel_row['id']

        # Get address components
        try:
            parcel_address = Address(street_address)
        except ValueError:
            # TODO: this should never happen
            print('Could not parse parcel address: {}'.format(street_address))
            continue

        street_full = parcel_address.street_full
        address_low = parcel_address.address_low
        address_low_suffix = parcel_address.address_low_suffix
        address_high = parcel_address.address_high
        
        parcel_map.setdefault(street_address, [])
        parcel_map[street_address].append(row_id)

        block_map.setdefault(street_full, {})
        hundred_block = parcel_address.hundred_block
        block_map[street_full].setdefault(hundred_block, [])

        # Add a few address components used below
        parcel_row['address_low'] = parcel_address.address_low
        parcel_row['address_high'] = parcel_address.address_high
        parcel_row['address_low_suffix'] = parcel_address.address_low_suffix
        parcel_row['unit_full'] = parcel_address.unit_full
        block_map[street_full][hundred_block].append(parcel_row)

    print('Relating addresses to parcels...')
    for address in addresses:
        address_low = address.address_low
        address_low_suffix = address.address_low_suffix
        address_unit_full = address.unit_full
        street_address = address.street_address
        matches = []  # dicts of {row_id, match_type}

        # EXACT
        if street_address in parcel_map:
            for row_id in parcel_map[street_address]:
                matches.append({
                    'parcel_row_id':    row_id,
                    'match_type':       'exact',
                })
        else:
            try:
                # BASE, BASE NO SUFFIX, GENERIC UNIT
                for variant_type in ['base_address', 'base_address_no_suffix',\
                    'generic_unit']:
                    variant = getattr(address, variant_type)

                    if variant in parcel_map:
                        row_ids = parcel_map[variant]
                        for row_id in row_ids:
                            match_type = ADDRESS_VARIANT_MATCH_TYPE[variant_type]
                            matches.append({
                                'parcel_row_id':    row_id,
                                'match_type':       match_type,
                            })                  
                            match_counts[match_type] += 1
                            raise ContinueIteration
                
            except ContinueIteration:
                pass

            # RANGES
            if len(matches) == 0:
                address_high = address.address_high
                street_full = address.street_full
                hundred_block = address.hundred_block
                address_parity = address.parity

                # ADDRESS IN PARCEL RANGE
                if street_full in block_map:
                    street_map = block_map[street_full]
                    parcels_on_block = street_map.get(hundred_block, [])
                    
                    for parcel_row in parcels_on_block:
                        # Check low/high, suffix
                        parcel_low = parcel_row['address_low']
                        parcel_high = parcel_row['address_high']

                        # Check unit
                        parcel_unit_full = parcel_row['unit_full']
                        if address_unit_full != parcel_unit_full:
                            continue

                        # Check suffix
                        parcel_low_suffix = parcel_row['address_low_suffix']
                        if address_low_suffix != parcel_low_suffix:
                            continue

                        # SINGLE ADDRESS => RANGE PARCEL
                        if address_high is None:
                            # Skip single addresses
                            if parcel_high is None:
                                continue

                            check_low = parcel_low
                            check_mid = address_low
                            check_high = parcel_high
                            
                            parcel_parity = \
                                parity_for_range(parcel_low, parcel_high)

                        # RANGE ADDRESS => SINGLE PARCEL(S)
                        else:
                            check_low = address_low
                            check_mid = parcel_low
                            check_high = address_high

                            parcel_parity = parity_for_num(parcel_low)

                        if parcel_parity != address_parity:
                            continue

                        # If it's in range
                        if check_low <= check_mid <= check_high:
                            row_id = parcel_row['id']

                            if address_high is None:
                                match_type = 'address_in_parcel_range'
                            else:
                                match_type = 'parcel_in_address_range'
                            match_counts[match_type] += 1
                            matches.append({
                                'parcel_row_id':        row_id,
                                'match_type':           match_type, 
                            })

        # Handle matches
        for match in matches:
            address_parcel = {
                'street_address':   street_address,
                'parcel_source':    parcel_layer,
            }
            address_parcel.update(match)
            address_parcels.append(address_parcel)

        # Rework this to support multiple matches
        # if parcel_id is not None:
        #   address_parcel = {
        #       'street_address':   street_address,
        #       'parcel_source':    parcel_layer,
        #       'parcel_id':        parcel_id,
        #       'match_type':       match_type,
        #   }
        #   address_parcels.append(address_parcel)

for ap in address_parcels:
    for key, value in ap.items():
        if isinstance(value, list):
            pprint(ap)
            sys.exit()

if WRITE_OUT:
    print('Writing address-parcels...')
    address_parcel_table.write(address_parcels, chunk_size=150000)
    print('Indexing address-parcels...')
    address_parcel_table.create_index('street_address')

for variant_type, count in match_counts.items():
    print('{} matched on {}'.format(count, variant_type))

del address_parcels


################################################################################
# ADDRESS-PROPERTIES
################################################################################

print('\n** ADDRESS-PROPERTIES **')

if WRITE_OUT:
    print('Dropping index on address-properties...')
    address_property_table.drop_index('street_address')
    print('Deleting existing address-properties...')
    address_property_table.delete()

# Read properties in
print('Reading properties from AIS...')
# TODO: clean this up, move config to config
prop_rows = db['opa_property'].read(fields=['street_address', 'account_num', 'address_low', 'address_high', 'unit_num'])
prop_map = {x['street_address']: x for x in prop_rows}

print('Indexing range properties...')
range_rows = [x for x in prop_rows if x['address_high'] is not None]
range_map = {}  # street_full => [range props]
for range_row in range_rows:
    street_address = range_row['street_address']
    street_full = Address(street_address).street_full
    prop_list = range_map.setdefault(street_full, [])
    prop_list.append(range_row)

address_props = []

print('Relating addresses to properties...')
for i, address in enumerate(addresses):
    if i % 100000 == 0:
        print(i)

    street_address = address.street_address
    unit_num = address.unit_num
    prop = None
    match_type = None

    # EXACT
    if street_address in prop_map:
        prop = prop_map[street_address]
        match_type = 'exact'

    # BASE
    elif unit_num and address.base_address in prop_map:
        prop = prop_map[address.base_address]
        match_type = 'base'

    # BASE NO SUFFIX
    elif address.base_address_no_suffix in prop_map:
        prop = prop_map[address.base_address_no_suffix]
        match_type = 'base_no_suffix'

    # GENERIC UNIT
    elif unit_num and address.generic_unit in prop_map:
        prop = prop_map[address.generic_unit]
        match_type = 'generic_unit'

    # RANGE
    elif address.address_high is None and address.street_full in range_map:
        range_props_on_street = range_map[address.street_full]
        address_parity = address.parity

        for range_prop in range_props_on_street:
            range_prop_address_low = range_prop['address_low']
            range_prop_address_high = range_prop['address_high']
            range_prop_parity = parity_for_range(range_prop_address_low, \
                range_prop_address_high)

            # Check parity
            if address_parity != range_prop_parity:
                continue

            if range_prop['address_low'] <= address.address_low <= range_prop['address_high']:
                # If there's a unit num we have to make sure that matches too
                if (address.unit_num or range_prop['unit_num']) and \
                    address.unit_num != range_prop['unit_num']:
                    continue

                prop = range_prop
                match_type = 'range'
                break

    if prop:
        address_prop = {
            'street_address':   street_address,
            'opa_account_num':  prop['account_num'],
            'match_type':       match_type,
        }
        address_props.append(address_prop)

if WRITE_OUT:
    address_property_table.write(address_props)
    print('Indexing address-properties...')
    address_property_table.create_index('street_address')


################################################################################
# TRUE RANGE
################################################################################

print('\n** TRUE RANGE **')

if WRITE_OUT:
    print('Creating true range view...')
    db.drop_view(true_range_view_name)
    db.create_view(true_range_view_name, true_range_select_stmt)


################################################################################
# ERRORS
################################################################################

print('\n** ERRORS **')

if WRITE_OUT:
    print('Writing errors...')
    address_error_table.write(address_errors, chunk_size=150000)

# print('{} errors'.format(error_count))
# print('{} warnings'.format(warning_count))

################################################################################
# FINISH
################################################################################

print('\n** FINISHING **')

if WRITE_OUT:
    print('Creating indexes...')
    index_tables = (
        address_table,
        address_tag_table,
        source_address_table,
    )
    for table in (address_table, address_tag_table, source_address_table):
        table.create_index('street_address')
    address_link_table.create_index('address_1')
    address_link_table.create_index('address_2')
    address_street_table.create_index('street_address')

db.close()

print('Finished in {} seconds'.format(datetime.now() - start))