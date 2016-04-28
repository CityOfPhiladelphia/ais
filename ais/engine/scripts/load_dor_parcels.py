import sys
import os
import csv
import re
from datetime import datetime
from phladdress.data import DIRS_STD, SUFFIXES_STD, UNIT_TYPES_STD
import datum
from ais.models import Address
from ais.util import parity_for_num, parity_for_range
from ais import app
# DEV
from pprint import pprint
import traceback


start = datetime.now()
print('Starting...')

"""SET UP"""

config = app.config
db = datum.connect(config['DATABASES']['engine'])

source_def = config['BASE_DATA_SOURCES']['parcels']['dor']
source_db_name = source_def['db']
source_db_url = config['DATABASES'][source_db_name]
source_db = datum.connect(source_db_url)
source_field_map = source_def['field_map']
source_table_name = source_def['table']
source_table = source_db[source_table_name]
source_geom_field = source_table.geom_field
field_map = source_def['field_map']

street_table = db['street_segment']
parcel_table = db['dor_parcel']
parcel_error_table = db['dor_parcel_error']
parcel_error_polygon_table = db['dor_parcel_error_polygon']
WRITE_OUT = True

# Regex
street_name_re = re.compile('^[A-Z0-9 ]+$')
unit_num_re = re.compile('^[A-Z0-9\-]+$')
parcel_id_re = re.compile('^\d{3}(N|S)\d{6}$')
geometry_re = re.compile('^(MULTI)?POLYGON')

"""MAIN"""

if WRITE_OUT:
    print('Dropping indexes...')
    parcel_table.drop_index('street_address')
    print('Deleting existing parcels...')
    parcel_table.delete()
    print('Deleting existing parcel errors...')
    parcel_error_table.delete()
    print('Deleting existing parcel error polygons...')
    parcel_error_polygon_table.delete()

print('Reading streets...')
street_stmt = '''
    select street_full, seg_id, street_code, left_from, left_to, right_from, right_to
    from {}
'''.format(street_table.name)
street_rows = db.execute(street_stmt)

street_code_map = {}  # street_full => street_code
street_full_map = {}  # street_code => street_full
seg_map = {}  # street_full => [seg rows]

for street_row in street_rows:
    street_code = street_row['street_code']
    street_full = street_row['street_full']

    seg_map.setdefault(street_full, [])
    seg_map[street_full].append(street_row)

    street_code_map[street_full] = street_code
    street_full_map[street_code] = street_full

# TODO: currently there's a problem with parsing street names where a
# single street_full will map to more than one street code. (It's dropping the
# RAMP suffix where it shouldn't be. Only a few instances of this and so just 
# override for now.
street_code_map.update({
    'VINE ST':      80120,
    'MARKET ST':    53560,
    'COMMERCE ST':  24500,
})
street_full_map.update({
    80120:          'VINE ST',
    53560:          'MARKET ST',
    24500:          'COMMERCE ST',
})

print('Reading parcels from source...')
# Get field names
source_where = source_def['where']

# DEV
# source_table += ' SAMPLE(1)'
# source_where += " AND mapreg = '001S050134'"
# source_where += " AND objectid = 540985"

source_fields = list(field_map.values())
source_parcels = source_table.read(where=source_where)
source_parcel_map = {x['objectid']: x for x in source_parcels}

parcels = []
parcel_map = {}             # object ID => parcel object

# QC
error_map = {}              # object ID => error string
warning_map = {}            # object ID => [warning strings]
object_id = None            # Make this global so the error functions work
should_add_parcel = None    # Declare this here for scope reasons
bad_geom_parcels = []       # Object IDs

address_counts = {}         # street_address => count
parcel_id_counts = {}       # parcel_id => count

# Use this to continue working on a parcel if one part of validation fails
# class KeepGoing(Exception):
#   pass

def had_warning(reason, note=None):
    global warning_map
    global object_id
    parcel_warnings = warning_map.setdefault(object_id, [])
    warning = {
        'reason':   reason,
        'note':     note if note else '',
    }
    parcel_warnings.append(warning)

def had_error(reason, note=None):
    global error_map
    global object_id
    global should_add_parcel
    parcel_errors = error_map.setdefault(object_id, [])
    error = {
        'reason':   reason,
        'note':     note if note else '',
    }
    parcel_errors.append(error)
    should_add_parcel = False

# Loop over source parcels
for i, source_parcel in enumerate(source_parcels):
    try:
        if i % 50000 == 0:
            print(i)

        should_add_parcel = True

        # Strip whitespace, null out empty strings, zeroes
        for field, value in source_parcel.items():
            if isinstance(value, str):
                value = value.strip()
                if len(value) == 0 or value == '0':
                    value = None
                source_parcel[field] = value
            elif value == 0:
                source_parcel[field] = None

        # Get attributes
        object_id = source_parcel[field_map['source_object_id']]
        address_low = source_parcel[field_map['address_low']]
        address_low_suffix = source_parcel[field_map['address_low_suffix']]
        address_high = source_parcel[field_map['address_high']]
        street_predir = source_parcel[field_map['street_predir']]
        street_name = source_parcel[field_map['street_name']]
        street_suffix = source_parcel[field_map['street_suffix']]
        street_postdir = source_parcel[field_map['street_postdir']]
        unit_num = source_parcel[field_map['unit_num']]
        street_code = source_parcel[field_map['street_code']]
        parcel_id = source_parcel[field_map['parcel_id']]
        geometry = source_parcel[source_geom_field]

        # Declare this here so the except clause doesn't bug out
        source_address = None
        
        # Set this flag to false if we handle any specific address errors.
        # If no specific errors are found, compare the parsed address to
        # the source address to flag parser modifications.
        should_check_street_full = True

        # QC: Check address components
        if street_predir and street_predir not in DIRS_STD:
            had_warning('Non-standard predir')
            should_check_street_full = False
        if street_postdir and street_postdir not in DIRS_STD:
            had_warning('Non-standard postdir')
            should_check_street_full = False
        if street_suffix and street_suffix not in SUFFIXES_STD:
            had_warning('Non-standard suffix')
            should_check_street_full = False
        if unit_num and unit_num_re and not unit_num_re.match(unit_num):
            had_warning('Invalid unit num')
            should_check_street_full = False

        # QC: Check street components
        if street_name is None:
            had_error('No street name')
        if street_code is None:
            had_warning('No street code')

        # Make street full
        if street_name:
            street_comps = [street_predir, street_name, street_suffix, \
                street_postdir]
            street_full = ' '.join([x for x in street_comps if x])

            # QC: Check if street full exists
            found_street_full = True
            if street_full not in street_code_map:
                found_street_full = False
                note = 'Unknown street: {}'.format(street_full)
                had_error('Unknown street', note=note)

            if street_code:
                # QC: Check if street code exists
                if street_code not in street_full_map:
                    had_warning('Unknown street code')

                # QC: Check if street full matches street code
                elif found_street_full and \
                    street_code_map[street_full] != street_code:
                    actual_street = street_full_map[street_code]
                    note = 'Street code {} => {}'.format(street_code, actual_street)
                    had_warning('Incorrect street code', note=note)

        # QC: Check for low address number
        if address_low is None:
            had_error('No address number')

        # Clean up
        if address_high == 0:
            address_high = None

        address_low_fractional = None
        if address_low_suffix == '2':
            address_low_fractional = '1/2'
            address_low_suffix = None
        
        # Handle ranges
        if address_low and address_high:
            address_low_str = str(address_low)
            address_high_str = str(address_high)
            len_address_low = len(address_low_str)
            len_address_high = len(address_high_str)
            address_high_full = None

            if len(address_high_str) != 2:
                had_warning('High address should be two digits')

            if not address_high_str.isnumeric():
                address_high = None
                had_warning('Invalid high address')

            if address_high:
                # Case: 1234-36 or 1234-6
                if len_address_high < len_address_low:
                    # Make address high full and compare to address low
                    address_high_prefix = address_low_str[:-len_address_high]
                    address_high_full = int(address_high_prefix + address_high_str)
                # Cases: 1234-1236 or 2-12
                elif len_address_low == len_address_high or \
                    (len_address_low == 1 and len_address_high == 2):
                    address_high_full = address_high
                else:
                    had_error('Address spans multiple hundred blocks')

                # Case: 317-315
                if address_high_full:
                    if address_high_full < address_low:
                        # print(address_low, address_high_full)
                        had_error('Inverted range address')

                    # Make sure both addresses are on the same hundred block
                    hun_block_low = address_low - (address_low % 100)
                    hun_block_high = address_high_full - (address_high_full % 100)
                    if hun_block_low != hun_block_high:
                        # print(hun_block_low, hun_block_high)
                        had_error('Address spans multiple hundred blocks')

                    address_high = str(address_high_full)[-2:]

        # Make address full
        address_full = None
        if address_low:
            address_full = str(address_low)
            if address_low_suffix:
                address_full += address_low_suffix
            if address_low_fractional:
                address_full += ' ' + address_low_fractional
            if address_high:
                address_full += '-' + str(address_high)

        # Get unit
        unit_full = None
        if unit_num:
            unit_full = '# {}'.format(unit_num)
        
        address = None
        
        if address_full and street_full:
            source_address_comps = [address_full, street_full, unit_full]
            source_address = ' '.join([x for x in source_address_comps if x])

            # Try to parse
            try:
                address = Address(source_address)

                # QC: check for miscellaneous parcel modifications
                street_address = address.street_address
                if should_check_street_full and source_address != street_address:
                    note = 'Parser changes: {} => {}'.format(source_address, street_address)
                    had_warning('Parser changes', note=note)

                # QC: check for duplicate address
                address_counts.setdefault(street_address, 0)
                address_counts[street_address] += 1
            
            except Exception as e:
                print(source_address)
                had_error('Could not parse')

        # QC: parcel ID (aka mapreg)
        if parcel_id is None:
            had_error('No parcel ID')
        else:
            # Check for duplicate
            parcel_id_counts.setdefault(parcel_id, 0)
            parcel_id_counts[parcel_id] += 1

            if not parcel_id_re.match(parcel_id):
                had_warning('Invalid parcel ID')

        # QC: geometry
        if not geometry_re.match(geometry):
            had_error('Invalid geometry')
            bad_geom_parcels.append(object_id)

        '''
        STREET MATCH
        '''

        if address:
            # Get the parsed street_full
            street_full = address.street_full

            if street_full in seg_map:
                address_low = address.address_low
                address_high = address.address_high
                street_full = address.street_full
                address_parity = parity_for_num(address_low)
                matching_segs = seg_map[street_full]
                matching_seg = None
                matching_side = None
                had_alias = False  # TODO: check for aliases

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

                    # If it's in range
                    if check_from <= address_low <= check_to:
                        # And it's a single address
                        if address_high is None:
                            matching_seg = seg
                            break
                        # Otherwise if it's a range address
                        else:
                            # If we already had a match, flag multiple matches
                            if matching_seg:
                                seg_ids = sorted([x['seg_id'] for x in [matching_seg, seg]])
                                note = ','.join([str(x) for x in seg_ids])
                                had_warning('Range address matches multiple street segments', note=note)
                                
                            # Check if the high address is greater than the street max
                            if check_to < address_high:
                                # Otherwise, make the match and keep looking (in case
                                # it matches to multiple segments)
                                had_warning('High address out of street range')
                            
                            matching_seg = seg

                if matching_seg is None:
                    had_error('Out of street range')
                    should_add_parcel = False

        '''
        END STREET MATCH
        '''

        # Make parcel object
        if should_add_parcel:
            parcel = dict(address)
            parcel.update({
                'parcel_id':        parcel_id,
                'source_object_id': object_id,
                'source_address':   source_address,
                'geom':             geometry,
            })
            parcels.append(parcel)
            parcel_map[object_id] = parcel

    # except ValueError as e:
    #   # print('Parcel {}: {}'.format(parcel_id, e))
    #   reason = str(e)
    #   had_error(reason)

    except Exception as e:
        print('{}: Unhandled error'.format(source_parcel))
        print(parcel_id)
        print(traceback.format_exc())
        sys.exit()

print('Checking for duplicates...')

# Check for duplicate parcel IDs. Use source parcels for most results.
for source_parcel in source_parcels:
    # Set object ID here so logging function works
    object_id = source_parcel['objectid']
    parcel_id = source_parcel['mapreg']
    count = parcel_id_counts.get(parcel_id, 0)
    if count > 1:
        note = 'Parcel ID count: {}'.format(count)
        had_warning('Duplicate parcel ID', note=note)

# Check for duplicate addresses. Use parcels since source parcels don't have
# an address.
for parcel in parcels:
    # Set object ID here so logging function works
    object_id = parcel['source_object_id']
    street_address = parcel['street_address']
    count = address_counts.get(street_address, 0)
    if count > 1:
        note = 'Address count: {}'.format(count)
        had_warning('Duplicate address', note=note)

# Remember how many parcels we went through before we delete them all
parcel_count = len(parcels)

if WRITE_OUT:
    print('Writing parcels...')
    parcel_table.write(parcels, chunk_size=50000)

    print('Writing parcel errors...')
    errors = []
    source_non_geom_fields = [x for x in source_fields if x != source_geom_field]

    for level in ['error', 'warning']:
        issue_map = error_map if level == 'error' else warning_map
        
        for object_id, issues in issue_map.items():
            for issue in issues:
                reason = issue['reason']
                note = issue['note']
                source_parcel = source_parcel_map[object_id]
                
                # Make error row
                error = {x: source_parcel[x] if source_parcel[x] is not None \
                    else '' for x in source_non_geom_fields}

                # Make this work for integer fields
                if error['house'] == '':
                    error['house'] = None
                if error['stcod'] == '':
                    error['stcod'] = None

                error.update({
                    'level':    level,
                    'reason':   reason,
                    'notes':    note,
                })
                errors.append(error)

    parcel_error_table.write(errors, chunk_size=150000)
    del errors

    print('Writing parcel error polygons...')
    error_polygons = []

    for level in ['error', 'warning']:
        issue_map = error_map if level == 'error' else warning_map

        for object_id, issues in issue_map.items():
            # If this object had a geometry error, skip
            if object_id in bad_geom_parcels:
                continue

            # Roll up reasons, notes
            reasons = [x['reason'] for x in issues]
            reasons_joined = '; '.join(sorted(reasons))
            notes = [x['note'] for x in issues if x['note'] != '']
            notes_joined = '; '.join(notes)
            source_parcel = source_parcel_map[object_id]
            
            # Make error row
            error_polygon = {x: source_parcel[x] if source_parcel[x] is not None \
                else '' for x in source_fields}

            # Add/clean up fields
            if error_polygon['house'] == '':
                error_polygon['house'] = None
            if error_polygon['stcod'] == '':
                error_polygon['stcod'] = None

            error_polygon.update({
                'reasons':      reasons_joined,
                'reason_count': len(reasons),
                'notes':        notes_joined,
                # 'shape':        source_parcel[wkt_field],
            })
            error_polygons.append(error_polygon)

    parcel_error_polygon_table.write(error_polygons, chunk_size=50000)
    del error_polygons

    print('Creating indexes...')
    parcel_table.create_index('street_address')
    # TODO: index error tables?

source_db.close()
db.close()

print('Finished in {} seconds'.format(datetime.now() - start))
print('Processed {} parcels'.format(parcel_count))
print('{} errors'.format(len(error_map)))
print('{} warnings'.format(len(warning_map)))
