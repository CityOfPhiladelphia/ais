import sys
# import os
# import csv
# from math import sin, cos, atan2, radians, pi, degrees
from datetime import datetime
from shapely.wkt import loads, dumps
from shapely.geometry import Point, LineString, MultiLineString
import datum
from ais import app, util
from ais.models import Address
# DEV
import traceback
# from pprint import pprint

def main():
    start = datetime.now()
    print('Starting...')

    '''
    SET UP
    '''

    config = app.config
    engine_srid = config['ENGINE_SRID']
    Parser = config['PARSER']
    parser = Parser()
    db = datum.connect(config['DATABASES']['engine'])
    engine_srid = config['ENGINE_SRID']

    # parcel_table = 'pwd_parcel'
    parcel_layers = config['BASE_DATA_SOURCES']['parcels']
    address_table = db['address']
    address_fields = [
        'id',
        'street_address',
        'address_low',
        'address_high',
    ]
    seg_table = db['street_segment']
    seg_fields = [
        'seg_id',
        'left_from',
        'left_to',
        'right_from',
        'right_to',
    ]
    geocode_table = db['geocode']
    parcel_curb_table = db['parcel_curb']
    curb_table = db['curb']
    addr_street_table = db['address_street']
    addr_parcel_table = db['address_parcel']
    true_range_view = db['true_range']
    centerline_offset = config['GEOCODE']['centerline_offset']
    centerline_end_buffer = config['GEOCODE']['centerline_end_buffer']
    geocode_priority_map = config['ADDRESS_SUMMARY']['geocode_priority']
    WRITE_OUT = True

    # DEV - use this to work on only one street name at a time
    # TODO move this to config somewhere
    FILTER_STREET_NAME = ''
    WHERE_STREET_NAME = None
    WHERE_STREET_ADDRESS_IN = None
    WHERE_SEG_ID_IN = None
    if FILTER_STREET_NAME not in [None, '']:
        WHERE_STREET_NAME = "street_name = '{}'".format(FILTER_STREET_NAME)
        WHERE_STREET_ADDRESS_IN = "street_address in (select street_address from \
            {} where {})".format(address_table.name, WHERE_STREET_NAME)
        WHERE_SEG_ID_IN = "seg_id in (select seg_id from {} where {})" \
            .format(seg_table.name, WHERE_STREET_NAME)

    if WRITE_OUT:
        print('Dropping indexes...')
        geocode_table.drop_index('street_address')

        print('Deleting existing XYs...')
        geocode_table.delete()

        print('Deleting spatial address-parcels...')
        spatial_stmt = '''
            DELETE FROM address_parcel
                WHERE match_type = 'spatial'
        '''
        db.execute(spatial_stmt)

    print('Reading streets from AIS...')
    seg_rows = seg_table.read(fields=seg_fields, geom_field='geom', \
                              where=WHERE_STREET_NAME)
    seg_map = {}
    seg_geom_field = seg_table.geom_field
    for seg_row in seg_rows:
        seg_id = seg_row['seg_id']
        seg = {
            'L': {
                'low': seg_row['left_from'],
                'high': seg_row['left_to'],
            },
            'R': {
                'low': seg_row['right_from'],
                'high': seg_row['right_to'],
            },
            'shape': loads(seg_row[seg_geom_field])
        }
        seg_map[seg_id] = seg

    print('Reading parcels...')
    parcel_xy_map = {}  # source name => parcel row id => centroid xy (Shapely)
    parcel_geom_map = {} # parcel row id => geom

    for parcel_layer_name, parcel_layer_def in parcel_layers.items():
        # source_name = parcel_source['name']
        source_table = parcel_layer_name + '_parcel'
        print('  - {}'.format(parcel_layer_name))

        # DEV
        parcel_where = ''
        if WHERE_STREET_NAME:
            parcel_where = '{} and '.format(WHERE_STREET_NAME)
        # if source_table == 'pwd_parcel':
        parcel_stmt = '''
            select
                id,
                ST_AsText(geom) as geom,
                st_astext(st_centroid(geom)) as centroid
            from {source_table}
            where {where} st_intersects(st_centroid(geom), geom)
            union
            select
                id,
                ST_AsText(geom) as geom,
                st_astext(st_pointonsurface(geom)) as centroid
            from {source_table}
            where {where} not st_intersects(st_centroid(geom), geom)
        '''.format(where=parcel_where, source_table=source_table)
        parcel_rows = db.execute(parcel_stmt)
        parcel_layer_xy_map = {}
        parcel_layer_geom_map = {}
        for parcel_row in parcel_rows:
            parcel_id = parcel_row['id']
            xy = loads(parcel_row['centroid'])
            poly = loads(parcel_row['geom'])
            parcel_layer_xy_map[parcel_id] = xy
            parcel_layer_geom_map[str(parcel_id)] = poly
        parcel_xy_map[parcel_layer_name] = parcel_layer_xy_map
        parcel_geom_map[parcel_layer_name] = parcel_layer_geom_map


    print('Reading true range...')
    true_range_rows = true_range_view.read(where=WHERE_SEG_ID_IN)
    for true_range_row in true_range_rows:
        seg_id = true_range_row['seg_id']
        seg_map[seg_id]['L']['true_low'] = true_range_row['true_left_from']
        seg_map[seg_id]['L']['true_high'] = true_range_row['true_left_to']
        seg_map[seg_id]['R']['true_low'] = true_range_row['true_right_from']
        seg_map[seg_id]['R']['true_high'] = true_range_row['true_right_to']

    # TODO: redo curb stuff so it works with multiple parcel sources
    print('Reading curbs...')
    curb_rows = curb_table.read(to_srid=engine_srid)
    curb_map = {x['curb_id']: loads(x['geom']) for x in curb_rows}

    print('Reading parcel-curbs...')
    parcel_curb_map = {}  # parcel_source => parcel_id => curb_id
    parcel_curb_rows = parcel_curb_table.read()
    dor_parcel_curb_map = {str(x['parcel_row_id']): x['curb_id'] for x in parcel_curb_rows if x['parcel_source'] == 'dor'}
    pwd_parcel_curb_map = {str(x['parcel_row_id']): x['curb_id'] for x in parcel_curb_rows if x['parcel_source'] == 'pwd'}
    parcel_curb_map['dor'] = dor_parcel_curb_map
    parcel_curb_map['pwd'] = pwd_parcel_curb_map

    # with open("parcel_curb_map_output.txt", "w") as text_file:
    #     print("parcel_curb_map: {}".format(parcel_curb_map), file=text_file)

    print('Reading addresses from AIS...')
    address_rows = address_table.read(fields=address_fields, \
                                      where=WHERE_STREET_NAME)
    # where='street_address = \'2653-55 N ORIANNA ST\'')

    addresses = []
    seg_side_map = {}

    # for address_row in address_rows:
    # 	street_address = address_row['street_address']
    # 	address = Address(street_address)
    # 	addresses.append(address)

    # addresses = Address.query.all()

    # TODO: index by seg ID, side (seg_side_map above)
    # For interpolating between parcel centroids
    # if address_row['seg_id']:
    # 	seg_id = address_row['seg_id']
    # 	seg_side = address_row['seg_side']
    # 	if seg_id in seg_side_map:
    # 		sides = seg_side_map[seg_id]
    # 		if seg_side in sides:
    # 			sides[seg_side].append(address)
    # 		else:
    # 			sides[seg_side] = [address]
    # 	else:
    # 		seg_side_map[seg_id] = {
    # 			seg_side: [address]
    # 		}

    print('Reading address-streets...')
    addr_street_rows = addr_street_table.read(where=WHERE_STREET_ADDRESS_IN)
    # Create map: street_address => address-street row
    addr_street_map = {x['street_address']: x for x in addr_street_rows}

    print('Reading address-parcels...')
    addr_parcel_rows = addr_parcel_table.read(where=WHERE_STREET_ADDRESS_IN)

    # Create map: street address => parcel source => [parcel object ids]
    addr_parcel_map = {}
    for addr_parcel_row in addr_parcel_rows:
        street_address = addr_parcel_row['street_address']
        parcel_source = addr_parcel_row['parcel_source']
        parcel_row_id = addr_parcel_row['parcel_row_id']

        addr_parcel_map.setdefault(street_address, {})
        addr_parcel_map[street_address].setdefault(parcel_source, [])
        addr_parcel_map[street_address][parcel_source].append(parcel_row_id)

    '''
    MAIN
    '''

    print('Geocoding addresses...')
    geocode_rows = []
    geocode_count = 0

    # address-parcels to insert from spatial match
    address_parcels = []

    for i, address_row in enumerate(address_rows):
        try:
            if i % 50000 == 0:
                print(i)

            if i % 150000 == 0:
                geocode_table.write(geocode_rows)
                geocode_count += len(geocode_rows)
                geocode_rows = []

            address_id = address_row['id']
            street_address = address_row['street_address']
            address_low = address_row['address_low']
            address_high = address_row['address_high']

            # Get mid-address of ranges
            if address_high:
                # This is not necessarily an integer, nor the right parity, but
                # it shouldn't matter for interpolation.
                address_mid_offset = (address_high - address_low) / 2
                address_num = address_low + address_mid_offset
            else:
                address_num = address_low

            # Get seg ID
            try:
                addr_street_row = addr_street_map[street_address]
                seg_id = addr_street_row['seg_id']
                seg_side = addr_street_row['seg_side']
            except KeyError:
                seg_id = None
                seg_side = None

            # Get seg XY
            seg_shp = None  # use this in curbside later
            if seg_id:

                '''
                CENTERLINE
                '''

                # Get seg XY
                seg = seg_map[seg_id]
                seg_shp = seg['shape']

                # Interpolate using full range
                low = seg[seg_side]['low']
                high = seg[seg_side]['high']
                side_delta = high - low
                # seg_estimated = False

                # If the there's no range
                if side_delta == 0:
                    # print('No range: seg {}, {} - {}'.format(seg_id, low, high))
                    # continue
                    # Put it in the middle
                    distance_ratio = 0.5
                # seg_estimated = True
                else:
                    distance_ratio = (address_num - low) / side_delta
                # print('Distance ratio: {}'.format(distance_ratio))

                # Old method: just interpolate
                # seg_xsect_xy_old = seg_shp.interpolate(distance_ratio, \
                # 	normalized=True)
                # print('Old intersect: {}'.format(seg_xsect_xy_old))

                # New method: interpolate buffered
                seg_xsect_xy = util.interpolate_buffered(seg_shp, distance_ratio, \
                                                         centerline_end_buffer)
                # print('Intersect: {}'.format(seg_xsect_xy))

                seg_xy = util.offset(seg_shp, seg_xsect_xy, centerline_offset, \
                                     seg_side)
                # print('Offset to {}: {}'.format(seg_side, seg_xy))
                geocode_rows.append({
                    # 'address_id': address_id,
                    'street_address': street_address,
                    'geocode_type': geocode_priority_map['centerline'],
                    # 'estimated': '1' if seg_estimated else '0',
                    'geom': dumps(seg_xy)
                })

                '''
                TRUE RANGE
                '''

                true_low = seg[seg_side]['true_low']
                true_high = seg[seg_side]['true_high']
                true_side_delta = true_high - true_low
                # true_estimated = False

                if true_side_delta == 0:
                    # print('No true range: {}, seg {}, {} - {}'.format(seg_id, true_low, true_high))
                    # continue
                    true_distance_ratio = 0.5
                # true_estimated = True
                else:
                    true_distance_ratio = (address_num - true_low) / true_side_delta

                # true_xsect_xy = seg_shp.interpolate(true_distance_ratio, \
                # 	normalized=True)
                true_xsect_xy = util.interpolate_buffered(seg_shp, true_distance_ratio, \
                                                          centerline_end_buffer)
                true_seg_xy = util.offset(seg_shp, true_xsect_xy, centerline_offset, \
                                          seg_side)
                # print('true: {}'.format(true_seg_xy))
                geocode_rows.append({
                    # 'address_id': address_id,
                    'street_address': street_address,
                    'geocode_type': geocode_priority_map['true_range'],
                    # 'estimated': '1' if true_estimated else '0',
                    'geom': dumps(true_seg_xy)
                })

            '''
            PARCELS
            '''

            for parcel_layer_name, parcel_layer in parcel_layers.items():
                source_table = parcel_layer_name + '_parcel'
                # set these to None to avoid next address inheritance
                parcel_ids = None
                parcel_id = None
                parcel_xy = None
                try:
                    parcel_ids = addr_parcel_map[street_address][parcel_layer_name]
                except KeyError as e:
                    # TODO: check if there's an address link that points to an
                    # address in address_parcel
                    parcel_ids = None

                # Get parcel XY
                if parcel_ids:
                    # Single parcel match
                    if len(parcel_ids) == 1:
                        parcel_id = parcel_ids[0]
                        parcel_xy = parcel_xy_map[parcel_layer_name][parcel_id]
                        geocode_rows.append({
                            # 'address_id': address_id,
                            'street_address': street_address,
                            'geocode_type': geocode_priority_map[source_table],
                            # 'estimated': 		'0',
                            'geom': dumps(parcel_xy)
                        })

                    # Multiple parcel matches
                    else:
                        # TODO: could get the combined centroid of the parcels,
                        # if they're adjacent
                        # print('{}: {} parcel matches'.format(street_address, len(parcel_ids)))
                        # num_multiple_parcel_matches += 1
                        parcel_id = None
                        parcel_xy = None

                elif seg_id:
                    '''
                    SPATIAL MATCH
                    '''

                    for test_offset in range(10, 50, 10):
                        # Get test XY
                        test_xy_shp = util.offset(seg_shp, true_xsect_xy, \
                                                  test_offset, seg_side)
                        test_xy_wkt = dumps(test_xy_shp)

                        parcel_match_stmt = '''
                            SELECT
                                id,
                                CASE
                                    WHEN ST_Intersects(geom, ST_Centroid(geom))
                                    THEN ST_AsText(ST_Centroid(geom))
                                    ELSE ST_AsText(ST_PointOnSurface(geom))
                                END as wkt
                            FROM {source_table}
                            WHERE ST_Intersects(geom, ST_GeomFromText('{test_xy_wkt}', {engine_srid}))
                        '''.format(source_table=source_table, test_xy_wkt=test_xy_wkt, engine_srid=engine_srid)
                        db.execute(parcel_match_stmt)
                        parcel_match = db._c.fetchone()

                        if parcel_match:
                            parcel_id = parcel_match['id']
                            # pwd_parcel_id = parcel_match['parcel_id']
                            # pwd_parcel_xy = parcel_xy_map[parcel_layer_name][parcel_id]
                            # print('Rematched {} to PWD parcel {}'.format(street_address, pwd_parcel_id))
                            parcel_match_wkt = parcel_match['wkt']
                            geocode_rows.append({
                                'street_address': street_address,
                                'geocode_type': geocode_priority_map[source_table + '_spatial'],
                                # 'estimated': '1',
                                # 'geometry': dumps(pwd_parcel_xy)
                                'geom': parcel_match_wkt,
                            })

                            # Make estimated address-parcel
                            address_parcels.append({
                                'street_address': street_address,
                                'parcel_source': parcel_layer_name,
                                'parcel_row_id': parcel_id,
                                'match_type': 'spatial',
                            })

                            break

                '''
                CURBSIDE & IN_STREET (MIDPOINT B/T CURB & CENTERLINE)
                '''

                if seg_id and parcel_id and parcel_xy:
                    # TODO: use pwd parcel if matched spatially
                    parcel_id = str(parcel_id)
                    if parcel_id in parcel_curb_map[parcel_layer_name] and seg_shp is not None:
                        curb_id = parcel_curb_map[parcel_layer_name][parcel_id]
                        curb_shp = curb_map[curb_id]

                        # Project parcel centroid to centerline
                        # if parcel_xy:
                        proj_dist = seg_shp.project(parcel_xy)
                        proj_xy = seg_shp.interpolate(proj_dist)
                        proj_shp = LineString([parcel_xy, proj_xy])

                        # Get point of intersection and add
                        curb_xsect_line_shp = curb_shp.intersection(proj_shp)
                        curb_xsect_pt = None
                        if isinstance(curb_xsect_line_shp, LineString):
                            try: 
                                curb_xsect_pt = curb_xsect_line_shp.coords[1]
                            # If no coords returned from our intersection, pass. 
                            except IndexError: 
                                pass
                        elif isinstance(curb_xsect_line_shp, MultiLineString):
                            curb_xsect_pt = curb_xsect_line_shp[-1:][0].coords[1]
                        if curb_xsect_pt:
                            xy_on_curb_shp = Point(curb_xsect_pt)
                            curb_geocode_row = {
                                'street_address': street_address,
                                'geocode_type': geocode_priority_map[parcel_layer_name + '_curb'],
                                'geom': dumps(xy_on_curb_shp)
                            }
                            # Get midpoint between centerline and curb
                            xy_in_street = (proj_xy.x + curb_xsect_pt[0]) / 2, (proj_xy.y + curb_xsect_pt[1]) / 2
                            xy_in_st_shape = Point(xy_in_street)
                            in_st_geocode_row = {
                                'street_address': street_address,
                                'geocode_type': geocode_priority_map[parcel_layer_name + '_street'],
                                'geom': dumps(xy_in_st_shape)
                            }
                            geocode_rows.append(curb_geocode_row)
                            geocode_rows.append(in_st_geocode_row)

                        # PWD centroid geocoded to front of building/parcel
                        if parcel_id in parcel_geom_map[parcel_layer_name]:
                            # print(parcel_id)
                            parcel_geom = parcel_geom_map[parcel_layer_name][parcel_id]
                            parcel_front_xsect_line_shp = parcel_geom.intersection(proj_shp)
                            parcel_front_xsect_pt = None
                            if isinstance(parcel_front_xsect_line_shp, LineString):
                                parcel_front_xsect_pt = parcel_front_xsect_line_shp.coords[1]
                            elif isinstance(parcel_front_xsect_line_shp, MultiLineString):
                                parcel_front_xsect_pt = parcel_front_xsect_line_shp[-1:][0].coords[1]
                            if parcel_front_xsect_pt:
                                xy_on_parcel_front_shp = Point(parcel_front_xsect_pt)
                                parcel_front_geocode_row = {
                                    'street_address': street_address,
                                    'geocode_type': geocode_priority_map[parcel_layer_name + '_parcel_front'],
                                    'geom': dumps(xy_on_parcel_front_shp)
                                }
                                geocode_rows.append(parcel_front_geocode_row)

        except ValueError as e:
            print(e)

        except Exception as e:
            print(traceback.format_exc())
            raise e

    if WRITE_OUT:
        print('Writing XYs...')
        geocode_table.write(geocode_rows, chunk_size=150000)

        print('Writing address-parcels...')
        # db.drop_index('address_parcel', 'street_address')
        addr_parcel_table.write(address_parcels, chunk_size=150000)
        # db.create_index('address_parcel', 'street_address')

        # print('Creating index...')
        # geocode_table.create_index('street_address')

        print('Wrote {} rows'.format(len(geocode_rows) + geocode_count))


    print('Creating index...')
    geocode_table.create_index('street_address')

    db.close()

    print('Finished in {}'.format(datetime.now() - start))
