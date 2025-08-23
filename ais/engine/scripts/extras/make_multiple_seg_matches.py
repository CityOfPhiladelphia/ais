"""
This script reads through range addresses where the low num and high num match
to different street segments and creates lines from the address's parcel XY
(where available) to nearest point on the matched street segment.
"""

from copy import copy
import sys
# from datetime import datetime
from phladdress.parser import Parser
from db.connect import connect_to_db
from models.address import Address
from config import CONFIG
from shapely.geometry import LineString
from shapely.wkt import loads, dumps
from util.util import parity_for_num, parity_for_range
# DEV
import traceback
from pprint import pprint

MULTI_SEG_TABLE = 'multiple_seg_line'
PARCEL_SOURCES = [
	'pwd_parcel',
	'dor_parcel',
]
WRITE_OUT = True

print('Starting...')

ais_db = connect_to_db(CONFIG['db']['ais_work'])

if WRITE_OUT:
	print('Dropping existing multiple seg lines...')
	ais_db.truncate(MULTI_SEG_TABLE)

print('Reading streets...')
seg_rows = ais_db.read('street_segment', ['seg_id'], geom_field='geometry')
seg_geom_map = {x['seg_id']: loads(x['geometry_wkt']) for x in seg_rows}

print('Reading address-streets...')
addr_street_rows = ais_db.read('address_street', ['*'])
addr_street_map = {x['street_address']: x['seg_id'] for x in addr_street_rows}

print('Reading multiple-seg addresses...')
stmt = '''
	select sq.address_2 as street_address from
		(select adl.address_2, ads.seg_id
		from (
			select * from address_link where relationship = 'in range'
		) adl
		join address_street ads
		on adl.address_1 = ads.street_address
		group by adl.address_2, ads.seg_id) sq
	group by address_2
	having count(*) > 1
'''
ais_db.c.execute(stmt)
multi_rows = ais_db.c.fetchall()
multi_addrs = [x['street_address'] for x in multi_rows]

multi_seg_lines = []

for multi_addr in multi_addrs:
	# Get child addresses
	stmt = f'''
		select adl.address_1 from address_link adl
		join address a on
		adl.address_1 = a.street_address
		where
			adl.address_2 = '{multi_addr}' and
			adl.relationship = 'in range'
		order by a.address_low
	'''
	ais_db.c.execute(stmt)
	child_rows = [x['address_1'] for x in ais_db.c.fetchall()]

	low_address = child_rows[0]
	high_address = child_rows[-1]

	# Get parcel geocode for low address
	geocode_where = f"street_address = '{multi_addr}' and geocode_type in ('pwd_parcel', 'dor_parcel')"
	geocode_rows = ais_db.read('geocode', ['*'], geom_field='geometry', \
		where=geocode_where)
	# Sort by parcel priority
	geocode_rows = sorted(
		geocode_rows,
		key=lambda k: PARCEL_SOURCES.index(k['geocode_type']),
		reverse=True
	)
	try:
		geocode_row = geocode_rows[0]
		geocode_shp = loads(geocode_row['geometry_wkt'])
	except IndexError:
		#print(f'No parcel XY for {multi_addr}')
		continue

	# Get seg IDs
	try:
		low_seg_id = addr_street_map[low_address]
	except KeyError:
		print(multi_addr, low_address, high_address)

		sys.exit()
	high_seg_id = addr_street_map[high_address]

	# Get segs
	low_seg_shp = seg_geom_map[low_seg_id]
	high_seg_shp = seg_geom_map[high_seg_id]

	# Interpolate and project
	low_dist = low_seg_shp.project(geocode_shp)
	high_dist = high_seg_shp.project(geocode_shp)

	low_endpoint_shp = low_seg_shp.interpolate(low_dist)
	high_endpoint_shp = high_seg_shp.interpolate(high_dist)

	# Make lines
	low_line_shp = LineString([geocode_shp, low_endpoint_shp])
	high_line_shp = LineString([geocode_shp, high_endpoint_shp])

	low_multi_seg_line = {
		'street_address':	low_address,
		'parent_address':	multi_addr,
		'seg_id':			low_seg_id,
		'geometry':			dumps(low_line_shp),
		'parcel_source':	geocode_row['geocode_type'][:3]
	}
	high_multi_seg_line = {
		'street_address':	high_address,
		'parent_address':	multi_addr,
		'seg_id':			high_seg_id,
		'geometry':			dumps(high_line_shp),
		'parcel_source':	geocode_row['geocode_type'][:3]
	}

	multi_seg_lines += [low_multi_seg_line, high_multi_seg_line]

if WRITE_OUT:
	print('Writing multiple seg lines...')
	ais_db.bulk_insert(MULTI_SEG_TABLE, multi_seg_lines, geom_field='geometry', multi_geom=False)

ais_db.close()
