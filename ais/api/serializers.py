import json
from collections import OrderedDict
from ais import util, models
from geoalchemy2.shape import to_shape
from shapely import wkt
from ais import app, app_db as db
from itertools import chain

class BaseSerializer:
    def model_to_data(self, instance):
        raise NotImplementedError()

    def render(self, data):
        raise NotImplementedError()

    def serialize(self, instance):
        data = self.model_to_data(instance)
        return self.render(data)

    def serialize_many(self, instances):
        data = [self.model_to_data(instance) for instance in instances]
        return self.render(data)


class GeoJSONSerializer (BaseSerializer):
    def __init__(self, metadata=None, pagination=None, srid=4326):
        self.metadata = metadata
        self.pagination = pagination
        self.srid = srid
        super().__init__()

    def render(self, data):
        final_data = []
        if self.metadata:
            final_data += sorted(self.metadata.items(),reverse=True)

        # Render as a feature collection if in a list
        if isinstance(data, list):
            if self.pagination:
                final_data += self.pagination.items()
            final_data += [
                ('type', 'FeatureCollection'),
                ('features', data),
            ]

        # Render as a feature otherwise
        else:
            final_data += data.items()

        final_data = OrderedDict(final_data)
        return json.dumps(final_data)

    def get_address_link_relationships(self, street_address, base_address):
        link_stmt = '''
                        SELECT address_1, relationship, address_2
                        from address_link
                        where address_1 = '{street_address}' or address_2 = '{base_address}'
                    '''.format(street_address=street_address, base_address=base_address)
        link_addresses = db.engine.execute(link_stmt).fetchall()

        match_type = None
        related_addresses = []

        query_address_1_match_map = {
            'has base': 'exact',
            'matches unit': 'exact',
            'has generic unit': 'exact',
            'in range': 'exact'
        }
        query_address_2_match_map = {
            'has base': 'base_address',
            'matches unit': 'unit_sibling',
            'has generic unit': 'unit_sibling',
            'in range': 'range_child'
        }
        unit_address_1_match_map = {
            'has base': 'unit_child',
            'matches unit': 'unit_sibling',
            'has generic unit': 'unit_sibling',
            'in range': 'exact'
        }
        unit_address_2_match_map = {
            'has base': 'unit_sibling',
            'matches unit': 'unit_sibling',
            'has generic unit': 'unit_sibling',
            'in range': 'range_child'
        }

        if street_address == self.normalized_address:
            # Base query response address (not joined with flag(s))
            for link_address in link_addresses:
                #print(link_address)
                related_address = {}
                address_1 = link_address['address_1']
                address_2 = link_address['address_2']
                relationship = link_address['relationship']

                if address_1 == street_address:
                    print(1, link_address)
                    match_type = query_address_1_match_map[relationship]
                    related_address[link_address['address_2']] = relationship

                elif address_2 == street_address and street_address == self.base_address and relationship == 'has base':
                    print(2, link_address)
                    match_type = query_address_2_match_map[relationship] if match_type is None else match_type
                    related_address[link_address['address_1']] = unit_address_1_match_map[relationship]

                elif address_2 == street_address and relationship == 'in range':
                    match_type = query_address_1_match_map[relationship]
                    related_address[link_address['address_1']] = query_address_2_match_map[relationship]
                    print(3, link_address)

                elif address_2 == self.base_address and street_address != self.base_address and relationship == 'has base':
                    print(4, link_address)
                    related_address[link_address['address_1']] = 'unit_sibling'

                related_addresses.append(related_address)

        else:
            # include_units flag joined child_unit addresses
            #print(2, street_address, self.normalized_address)
            for link_address in link_addresses:
                related_address = {}
                address_1 = link_address['address_1']
                address_2 = link_address['address_2']
                relationship = link_address['relationship']

                if address_1 == street_address:
                    print(5, link_address)
                    match_type = unit_address_1_match_map[relationship]
                    related_address[link_address['address_2']] = query_address_2_match_map[relationship]
                    related_addresses.append(related_address)
                elif address_2 == base_address and street_address != self.normalized_address:
                    print(6, link_address)
                    related_address[link_address['address_1']] = unit_address_2_match_map[relationship]
                    related_addresses.append(related_address)

        return match_type, related_addresses


class AddressJsonSerializer (GeoJSONSerializer):
    excluded_tags = ('info_resident', 'info_company', 'voter_name')

    def __init__(self, geom_type='centroid', geom_source=None, in_street=False, normalized_address=None, base_address=None, **kwargs):
        self.geom_type = geom_type
        self.geom_source = geom_source
        self.in_street = in_street
        self.normalized_address = normalized_address
        self.base_address = base_address
        super().__init__(**kwargs)

    def geom_to_shape(self, geom):
        return util.geom_to_shape(
            geom, from_srid=models.ENGINE_SRID, to_srid=self.srid)

    def project_shape(self, shape):
        return util.project_shape(
            shape, from_srid=models.ENGINE_SRID, to_srid=self.srid)

    def shape_to_geodict(self, shape):
        from shapely.geometry import mapping
        data = mapping(shape)
        return OrderedDict([
            ('type', data['type']),
            ('coordinates', data['coordinates'])
        ])

    def transform_exceptions(self, data):
        """
        Handle specific exceptions in the formatting of data.
        """

        # Convert the recycling diversion rate to a percentage with fixed
        # precision.
        try:
            rate = float(data['properties']['recycling_diversion_rate'])
            data['properties']['recycling_diversion_rate'] = round(rate/100, 3)
        except:
            pass

        return data

    def model_to_data(self, address):

        from collections import Iterable, Generator

        shape = None
        geocode_response_type = None
        # Handle instances where query includes request arg 'parcel_geocode_location' which joins geom from geocode,
        # creating an iterable object
        if isinstance(address, Iterable) and not isinstance(address, Generator):

            address, parcel_geocode_location_shape, geocode_response_type = address
            # If joined geom is empty, keep shape = None and get shape by default from geocode_x, geocode_y
            shape = self.geom_to_shape(parcel_geocode_location_shape) if parcel_geocode_location_shape is not None else None

        if not shape:
            from shapely.geometry import Point
            shape = Point(address.geocode_x, address.geocode_y)

        shape = self.project_shape(shape)
        geom_data = self.shape_to_geodict(shape)
        geom_type = {'geocode_type': geocode_response_type} if geocode_response_type else {'geocode_type': address.geocode_type}
        geom_data.update(geom_type)
        geom_data.move_to_end('geocode_type', last=False)

        # Build the set of associated service areas
        sa_data = OrderedDict()
        for col in address.service_areas.__table__.columns:
            if col.name in ('id', 'street_address'):
                continue
            sa_data[col.name] = getattr(address.service_areas, col.name)

        # Get address link relationships
        match_type, related_addresses = self.get_address_link_relationships(address.street_address, self.base_address)

        # Build the address feature, then attach tags and service areas
        data = OrderedDict([
            ('type', 'Feature'),
            ('ais_feature_type', 'address'),
            ('match_type', match_type),
            ('properties', OrderedDict([
                ('street_address', address.street_address),
                ('address_low', address.address_low),
                ('address_low_suffix', address.address_low_suffix),
                ('address_low_frac', address.address_low_frac),
                ('address_high', address.address_high),
                ('street_predir', address.street_predir),
                ('street_name', address.street_name),
                ('street_suffix', address.street_suffix),
                ('street_postdir', address.street_postdir),
                ('unit_type', address.unit_type),
                ('unit_num', address.unit_num),
                ('street_full', address.street_full),
                ('street_code', address.street_code),
                ('seg_id', address.seg_id),
                ('zip_code', address.zip_code or None),
                ('zip_4', address.zip_4 if address.zip_4.isdigit() and len(address.zip_4) == 4 else ''),
                ('usps_bldgfirm', address.usps_bldgfirm),
                ('usps_type', address.usps_type),
                ('election_block_id', address.election_block_id),
                ('election_precinct', address.election_precinct),
                ('pwd_parcel_id', address.pwd_parcel_id or None),
                ('dor_parcel_id', address.dor_parcel_id or None),
                ('li_address_key', address.li_address_key),
                ('pwd_account_nums', address.pwd_account_nums.split('|') if address.pwd_account_nums else None),
                ('opa_account_num', address.opa_account_num or None),
                ('opa_owners', address.opa_owners.split('|') if address.opa_owners else None),
                ('opa_address', address.opa_address or None),
            ])),
            ('geometry', geom_data),
        ])

        data['properties'].update(sa_data)
        data['properties'].update({'related_addresses': related_addresses})

        data = self.transform_exceptions(data)

        return data


class IntersectionJsonSerializer (GeoJSONSerializer):

    def __init__(self, geom_type='centroid', geom_source=None, **kwargs):
        #self.geom_type = 'Point'
        #self.geom_source = geom_source
        super().__init__(**kwargs)

    def geom_to_shape(self, geom):
        return util.geom_to_shape(
            geom, from_srid=models.ENGINE_SRID, to_srid=self.srid)

    def project_shape(self, shape):
        return util.project_shape(
            shape, from_srid=models.ENGINE_SRID, to_srid=self.srid)

    def shape_to_geodict(self, shape):
        from shapely.geometry import mapping
        data = mapping(shape)
        return OrderedDict([
            ('type', data['type']),
            ('coordinates', data['coordinates'])
        ])

    def model_to_data(self, intersection):

        if intersection.geom is not None:
            from shapely.geometry import Point
            shape = to_shape(intersection.geom)
            shape = self.project_shape(shape)
            geom_data = self.shape_to_geodict(shape)
        else:
            geom_data = None

        # Build the intersection feature, then attach properties
        #num_ints = intersection.int_ids.count('|') + 1
        data = OrderedDict([
            ('type', 'Feature'),
            ('ais_feature_type', 'intersection'),
            ('match_type', 'exact'),
            ('properties', OrderedDict([
                #('intersection_ids', intersection.int_ids),
                #('number of intersection points', num_ints),
                ('street_1', OrderedDict([
                    ('street_code', intersection.street_1_code),
                    ('street_full', intersection.street_1_full),
                    ('street_name', intersection.street_1_name),
                    ('street_predir', intersection.street_1_predir),
                    ('street_postdir', intersection.street_1_postdir),
                    ('street_suffix', intersection.street_1_suffix),
                ])
                 ),
                ('street_2', OrderedDict([
                    ('street_code', intersection.street_2_code),
                    ('street_full', intersection.street_2_full),
                    ('street_name', intersection.street_2_name),
                    ('street_predir', intersection.street_2_predir),
                    ('street_postdir', intersection.street_2_postdir),
                    ('street_suffix', intersection.street_2_suffix),
                ])
                 ),
            ])),
            ('geometry', geom_data),
        ])

        return data


class CascadedSegJsonSerializer (GeoJSONSerializer):

    def __init__(self,  pcomps=None, null_address_comps=None, normalized_address=None, base_address=None, geom_type='centroid', geom_source=None, **kwargs):
        #self.geom_type = 'Point'
        #self.geom_source = geom_source
        self.pcomps = pcomps
        self.null_address_comps = null_address_comps
        self.normalized_address = normalized_address
        self.base_address = base_address
        self.address_low_num = pcomps['address_low']
        self.address_high_num = pcomps['address_high']
        super().__init__(**kwargs)

        print(pcomps)

    def linestring_to_midpoint(self, geom):
        return geom.centroid

    def geom_to_shape(self, geom):
        return util.geom_to_shape(
            geom, from_srid=models.ENGINE_SRID, to_srid=self.srid)

    def project_shape(self, shape):
        return util.project_shape(
            shape, from_srid=models.ENGINE_SRID, to_srid=self.srid)

    def shape_to_geodict(self, shape):
        from shapely.geometry import mapping
        data = mapping(shape)
        return OrderedDict([
            ('type', data['type']),
            ('coordinates', data['coordinates'])
        ])

    def model_to_data(self, cascadedsegment):
        sa_data = OrderedDict()
        if cascadedsegment.geom is not None:
            from shapely.geometry import Point
            config = app.config
            centerline_offset = config['GEOCODE']['centerline_offset']
            centerline_end_buffer = config['GEOCODE']['centerline_end_buffer']
            seg_side = "R" if cascadedsegment.right_from % 2 == self.address_low_num % 2 else "L"

            true_range_stmt = '''
                            Select true_left_from, true_left_to, true_right_from, true_right_to
                             from true_range
                             where seg_id = {seg_id}
                        '''.format(seg_id=cascadedsegment.seg_id)
            true_range_result = db.engine.execute(true_range_stmt).fetchall()
            true_range_result = list(chain(*true_range_result))
            if true_range_result:
                side_delta = true_range_result[3] - true_range_result[2] if seg_side =="R" \
                    else true_range_result[1] - true_range_result[0]
            else:
                side_delta = cascadedsegment.right_to - cascadedsegment.right_from if seg_side == "R" \
                    else cascadedsegment.left_to - cascadedsegment.left_from
            if side_delta == 0:
                distance_ratio = 0.5
            else:
                distance_ratio = (self.address_low_num - cascadedsegment.right_from) / side_delta

            shape = to_shape(cascadedsegment.geom)

            # New method: interpolate buffered
            seg_xsect_xy=util.interpolate_buffered(shape, distance_ratio, centerline_end_buffer)
            seg_xy = util.offset(shape, seg_xsect_xy, centerline_offset, seg_side)
            shape = self.project_shape(seg_xy)
            geom_data = self.shape_to_geodict(shape)
            geom_type = {'geocode_type': 'true range'}
            geom_data.update(geom_type)

            # Get address link relationships
            match_type, related_addresses = self.get_address_link_relationships(self.normalized_address, self.base_address)

            # GET INTERSECTING SERVICE AREAS TODO: include fields for service areas where st_intersects is false
            # service_areas = models.ServiceAreaPolygon.query \
            #          .filter(models.ServiceAreaPolygon.geom.ST_INTERSECTS(seg_xy))
            #
            stmt = '''
                SELECT layer_id, value
                from service_area_polygon
                where ST_Intersects(geom, ST_GeometryFromText('SRID=2272;{shape}'))
            '''.format(shape=seg_xy)
            result = db.engine.execute(stmt)

            for item in result.fetchall():
                sa_data[item[0]] = item[1]
        else:
            geom_data = None

        data = OrderedDict([
            ('type', 'Feature'),
            ('ais_feature_type', 'address'),
            ('match_type', 'estimated'),
            ('properties', OrderedDict([])),
            ('geometry', geom_data),
        ])

        data['properties'].update(self.pcomps)
        data['properties'].update(self.null_address_comps)
        data['properties'].update(sa_data)
        data['properties'].update({'related_addresses': related_addresses})
        #data = self.transform_exceptions(data)

        return data