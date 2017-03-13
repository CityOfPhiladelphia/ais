import json
from collections import OrderedDict
from ais import util, models
from geoalchemy2.shape import to_shape
from geoalchemy2.functions import ST_X, ST_Y
from shapely import wkt
from ais import app, app_db as db
config = app.config
from itertools import chain

tag_fields = config['ADDRESS_SUMMARY']['tag_fields']
tag_field_map = {}
for tag in tag_fields:
    tag_field_map[tag['tag_key']] = tag['name']


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

    # def check_srid(self, srid=None):


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

    def get_address_link_relationships(self, address=None, base_address=None, **kwargs):

        address = address
        base_address = base_address
        link_stmt = '''
                        SELECT address_1, relationship, address_2
                        from address_link
                        where address_1 = '{street_address}' or address_2 = '{base_address}'
                    '''.format(street_address=address.street_address, base_address=base_address)
        link_addresses = db.engine.execute(link_stmt).fetchall()

        match_type = None
        related_addresses = []

        query_address_1_match_map = {
            'has base': 'exact',
            'matches unit': 'exact',
            'has generic unit': 'exact',
            'in range': 'exact',
            'overlaps': 'overlaps'
        }
        query_address_2_match_map = {
            'has base': 'base_address',
            'matches unit': 'unit_sibling',
            'has generic unit': 'unit_sibling',
            'in range': 'range_child',
            'overlaps': 'overlaps'
        }
        unit_address_1_match_map = {
            'has base': 'unit_child',
            'matches unit': 'unit_sibling',
            'has generic unit': 'unit_sibling',
            'in range': 'exact',
            'overlaps': 'overlaps'
        }
        unit_address_2_match_map = {
            'has base': 'unit_sibling',
            'matches unit': 'unit_sibling',
            'has generic unit': 'unit_sibling',
            'in range': 'range_child',
            'overlaps': 'overlaps'
        }
        street_address_variations = [address.street_address,
                                     address.street_address.replace(address.unit_type, "APT"),
                                     address.street_address.replace(address.unit_type, "UNIT"),
                                     address.street_address.replace(address.unit_type, "#")]


        # if address.street_address == self.normalized_address:
        # Add OR condition for unit type variations (i.e. address 337 S CAMAC ST APT 2R -> # 2R
        # if address.street_address == self.normalized_address or \
        #                 address.street_address.replace("#", "APT") == self.normalized_address or \
        #                 address.street_address.replace("#", "UNIT") == self.normalized_address:
        if self.normalized_address in street_address_variations:
            #print(0)
            # Base query response address (not joined with flag(s))
            for link_address in link_addresses:
                match_type = None
                related_address = {}
                address_1 = link_address['address_1']
                address_2 = link_address['address_2']
                relationship = link_address['relationship']

                # if address_1 == address.street_address:
                if address_1 in street_address_variations:
                    #print(1, link_address)
                    match_type = query_address_1_match_map[relationship]
                    #related_address[link_address['address_2']] = relationship

                # elif address_2 == address.street_address:
                elif address_2 in street_address_variations:
                    #print(2, link_address)
                    # if address.street_address == base_address:
                    if base_address in street_address_variations:
                        #print(3, link_address)
                        match_type = query_address_1_match_map[relationship]
                        #related_address[link_address['address_1']] = unit_address_2_match_map[relationship]
                    else:
                        #print(4, link_address)
                        match_type = query_address_1_match_map[relationship]
                        #related_address[link_address['address_1']] = query_address_2_match_map[relationship]

                #related_addresses.append(related_address)

        else:
            #print(00)
            # include_units flag joined child_unit addresses
            for link_address in link_addresses:
                related_address = {}
                address_1 = link_address['address_1']
                address_2 = link_address['address_2']
                relationship = link_address['relationship']

                # if address_1 == address.street_address:
                if address_1 in street_address_variations:
                    #print(5, link_address)
                    match_type = unit_address_1_match_map[relationship]
                    related_address[link_address['address_2']] = query_address_2_match_map[relationship]
                    #related_addresses.append(related_address)
                # elif address_2 == base_address and address.street_address != self.normalized_address:
                elif address_2 == base_address and self.normalized_address not in street_address_variations:
                    #print(6, link_address)
                    related_address[link_address['address_1']] = unit_address_2_match_map[relationship]
                    #related_addresses.append(related_address)

        return match_type#, related_addresses


class AddressJsonSerializer (GeoJSONSerializer):
    excluded_tags = ('info_resident', 'info_company', 'voter_name')

    def __init__(self, tag_data=None, geom_type=None, geom_source=None, normalized_address=None, base_address=None, shape=None, pcomps=None, sa_data=None, estimated=None, match_type=None, **kwargs):
        #self.geom_type = kwargs.get('geom_type') if 'geom_type' in kwargs else None
        self.geom_type = geom_type
        #self.geom_source = kwargs.get('geom_source') if 'geom_source' in kwargs else None
        self.geom_source = geom_source
        #self.normalized_address = kwargs.get('normalized_address') if 'normalized_address' in kwargs else None
        self.normalized_address = normalized_address
        #self.base_address = kwargs.get('base_address') if 'base_address' in kwargs else None
        self.base_address = base_address
        #self.shape = kwargs.get('shape') if 'shape' in kwargs else None
        self.shape = shape
        #self.estimated = True if 'estimated' in kwargs else False
        self.estimated = estimated
        #self.sa_data = kwargs.get('sa_data') if 'sa_data' in kwargs else None
        self.sa_data = sa_data
        self.match_type = match_type
        self.tag_data = tag_data
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

    def transform_tag_data(self, data, tag_data, address):
        """
        Handle specific exceptions in the formatting of data.
        """
        data_comps = []
        # VERSION FOR FLAT RESPONSE WITH ADDRESS TAG FIELDS AS DICTS WITH SOURCE ITEM
        render_source = OrderedDict()
        if not tag_data:
            return data_comps
        for rel_address in tag_data[address.street_address]:
            render_tag_data = {}
            tags = tag_data[address.street_address][rel_address]
            linked_path = tags[0] if tags[0] else address.street_address
            keyvals = tags[1]
            for key, val in keyvals.items():
                render_tag_data[key] = {'value': val, 'source': linked_path}
            render_source.update(render_tag_data)
        data_comps.append(render_source)

        return data_comps

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

        from collections import Iterable

        shape = self.project_shape(self.shape) if self.shape else None
        geocode_response_type = None
        # Handle instances where query includes request arg 'parcel_geocode_location' which joins geom from geocode,
        # creating an iterable object

        geom = None
        if isinstance(address, Iterable) and not self.estimated:

            address, geocode_response_type, geom = address
            gp_map = config['ADDRESS_SUMMARY']['geocode_priority']
            geocode_response_type = (list(gp_map.keys())[list(gp_map.values()).index(geocode_response_type)])

        cascade_geocode_type = self.estimated['cascade_geocode_type'] if self.estimated and self.estimated['cascade_geocode_type'] else None
        geom_type = {'geocode_type': geocode_response_type} if geocode_response_type else {'geocode_type': address.geocode_type} \
            if not self.estimated['cascade_geocode_type'] else {'geocode_type': self.estimated['cascade_geocode_type']}

        if cascade_geocode_type != 'parsed':
            shape = self.geom_to_shape(geom) if not shape else shape
            geom_data = self.shape_to_geodict(shape)
            geom_data.update(geom_type)
            geom_data.move_to_end('geocode_type', last=False)

            # Build the set of associated service areas
            sa_data = OrderedDict()
            if not self.estimated:
                for col in address.service_areas.__table__.columns:
                    if col.name in ('id', 'street_address'):
                        continue
                    sa_data[col.name] = getattr(address.service_areas, col.name)
            else:
                sa_data = self.sa_data

            # # Get address link relationships
                # # Version with match_type and related_addresses
            #match_type, related_addresses = self.get_address_link_relationships(address.street_address, self.base_address)
                # # Version without related_addresses
            match_type = self.get_address_link_relationships(address=address, base_address=self.base_address) if not self.estimated else 'unmatched'
            # Hack to get a match_type if address isn't in address_link table:
            match_type = 'exact' if not match_type else match_type
            match_type = self.match_type if self.match_type else match_type

        else:
            match_type = cascade_geocode_type
            geom_data = {'geocode_type': None, 'type': None, 'coordinates': None}
            sa_data = {}

        # Build the address feature, then attach tags and service areas
        data = OrderedDict([
            ('type', 'Feature'),
            ('ais_feature_type', 'address'),
            ('match_type', match_type if match_type else None),
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
                ('zip_code', {'source': '', 'value': ''}),
                ('zip_4', {'source': '', 'value': ''}),
                ('usps_bldgfirm', {'source': '', 'value': ''}),
                ('usps_type', {'source': '', 'value': ''}),
                ('election_block_id', {'source': '', 'value': ''}),
                ('election_precinct', {'source': '', 'value': ''}),
                ('pwd_parcel_id', {'source': '', 'value': ''}),
                ('dor_parcel_id', {'source': '', 'value': ''}),
                ('li_address_key', {'source': '', 'value': ''}),
                ('pwd_account_nums', {'source': '', 'value': ''}),
                ('opa_account_num', {'source': '', 'value': ''}),
                ('opa_owners', {'source': '', 'value': ''}),
                ('opa_address', {'source': '', 'value': ''}),
            ])),
            ('geometry', geom_data),
        ])

        data_comps = self.transform_tag_data(data, self.tag_data, address)
        if data_comps:
            for key, val in data_comps[0].items():
                key_name = tag_field_map[key]
                data['properties'][key_name] = val

        data = self.transform_exceptions(data)
        data['properties'].update(sa_data)

        return data


class IntersectionJsonSerializer (GeoJSONSerializer):

    def __init__(self, geom_type='centroid', geom_source=None, match_type=None, **kwargs):
        #self.geom_type = 'Point'
        #self.geom_source = geom_source
        self.match_type = match_type
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
            geom_type = {'geocode_type': 'intersection'}
            geom_data.update(geom_type)
        else:
            geom_data = OrderedDict([
                ('geocode_type', None),
                ('type', None),
                ('coordinates', None)
            ])

        # Build the intersection feature, then attach properties
        #num_ints = intersection.int_ids.count('|') + 1
        data = OrderedDict([
            ('type', 'Feature'),
            ('ais_feature_type', 'intersection'),
            ('match_type', self.match_type),
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


class ServiceAreaSerializer ():

    def __init__(self, coordinates=None, sa_data=None, metadata=None, **kwargs):
        #self.geom_type = 'Point'
        #self.geom_source = geom_source
        #self.match_type = match_type
        self.coordinates = coordinates
        self.sa_data = sa_data
        self.metadata = metadata
        super().__init__()

    def transform_exceptions(self, data):
        """
        Handle specific exceptions in the formatting of data.
        """

        # Convert the recycling diversion rate to a percentage with fixed
        # precision.
        try:
            rate = float(data['service_areas']['recycling_diversion_rate'])
            data['service_areas']['recycling_diversion_rate'] = round(rate/100, 3)
        except:
            pass

        return data

    def model_to_data(self):
        #sa_data = self.transform_exceptions(sa_data)
        data = {}
        sa_data_obj = {'service_areas': self.sa_data}
        data.update(self.metadata)
        data.update(sa_data_obj)
        return data

    def render(self, data):
        final_data = []
        if self.metadata:
            final_data += sorted(self.metadata.items(),reverse=True)

        # Render as a feature collection if in a list
        if isinstance(data, list):
            # if self.pagination:
            #     final_data += self.pagination.items()
            final_data += [
                ('type', 'FeatureCollection'),
                ('features', data),
            ]

        # Render as a feature otherwise
        else:
            final_data += data.items()

        final_data = OrderedDict(final_data)
        geom_data = OrderedDict([
            ('geocode_type', 'input'),
            ('type', 'Point'),
            ('coordinates', self.coordinates)
        ])
        final_data.update({'geometry': geom_data})
        return json.dumps(final_data)

    def serialize(self):
        data = self.model_to_data()
        data = self.transform_exceptions(data)
        return self.render(data)


class AddressTagSerializer():

    def __init__(self, address=None, tag_data=None, metadata=None, **kwargs):
        self.tag_data = tag_data
        self.metadata = metadata
        self.address = address
        super().__init__()

    def transform_tag_data(self, data, tag_data):
        """
        Handle specific exceptions in the formatting of data.
        """
        data_comps = []
        #print(tag_data)
        ## VERSION FOR TAGS GROUPED BY LINKED SOURCE
        # for rel_address in tag_data:
        #     render_tag_data = {}
        #     render_source = OrderedDict([
        #         ('street_address', ''),
        #         ('match_type', ''),
        #         ('properties', '')
        #     ])
        #     tags = tag_data[rel_address]
        #     linked_path = tags[0]
        #     render_source['street_address'] = rel_address
        #     render_source['match_type'] = linked_path if linked_path else 'exact'
        #     render_source['properties'] = []
        #     keyvals = tags[1]
        #     for key, val in keyvals.items():
        #         render_tag_data[key] = val
        #     render_source['properties'].append(render_tag_data)
        #     data_comps.append(render_source)

        # VERSION FOR FLAT RESPONSE WITH ADDRESS TAG FIELDS AS DICTS WITH SOURCE ITEM
        render_source = OrderedDict()
        print("tag_data: ", tag_data)
        for rel_address in tag_data:
            render_tag_data = {}
            tags = tag_data[rel_address]
            linked_path = tags[0] if tags[0] else 'exact'
            keyvals = tags[1]
            for key, val in keyvals.items():
                render_tag_data[key] = {'value': val, 'source': linked_path}
            render_source.update(render_tag_data)
        data_comps.append(render_source)

        return data_comps

    def model_to_data(self):
        data = {}
        data = OrderedDict([
            ('type', 'Feature'),
            ('ais_feature_type', 'address'),
            ('match_type', ''),
            ('properties', OrderedDict([
                ('street_address', self.address.street_address),
                ('address_low', self.address.address_low),
                ('address_low_suffix', self.address.address_low_suffix),
                ('address_low_frac', self.address.address_low_frac),
                ('address_high', self.address.address_high),
                ('street_predir', self.address.street_predir),
                ('street_name', self.address.street_name),
                ('street_suffix', self.address.street_suffix),
                ('street_postdir', self.address.street_postdir),
                ('unit_type', self.address.unit_type),
                ('unit_num', self.address.unit_num),
                ('street_full', self.address.street_full),

                #('street_code', self.address.street_code),
                #('seg_id', self.address.seg_id),

                ('zip_code', {'source': '', 'value': ''}),
                ('zip_4', {'source': '', 'value': ''}),
                ('usps_bldgfirm', {'source': '', 'value': ''}),
                ('usps_type', {'source': '', 'value': ''}),
                ('election_block_id', {'source': '', 'value': ''}),
                ('election_precinct', {'source': '', 'value': ''}),
                ('pwd_parcel_id', {'source': '', 'value': ''}),
                ('dor_parcel_id', {'source': '', 'value': ''}),
                ('li_address_key', {'source': '', 'value': ''}),
                ('pwd_account_nums', {'source': '', 'value': ''}),
                ('opa_account_num', {'source': '', 'value': ''}),
                ('opa_owners', {'source': '', 'value': ''}),
                ('opa_address', {'source': '', 'value': ''}),
            ])),
            ('geometry', {}),
        ])

        #data['properties'].update(sa_data)
        data.update(self.metadata)
        print(self.tag_data)
        data_comps = self.transform_tag_data(data, self.tag_data)
        #print(data_comps)
        for key, val in data_comps[0].items():
            key_name = tag_field_map[key]
            data['properties'][key_name] = val
        #data.update({'features': data_comps})
        return data

    def render(self, data):
        final_data = []
        if self.metadata:
            final_data += sorted(self.metadata.items(),reverse=True)
        # Render as a feature collection if in a list
        if isinstance(data, list):
            # if self.pagination:
            #     final_data += self.pagination.items()
            final_data += [
                ('type', 'FeatureCollection'),
                ('features', data),
            ]
        # Render as a feature otherwise
        else:
            final_data += data.items()

        final_data = OrderedDict(final_data)

        return json.dumps(final_data)

    def serialize(self):
        data = self.model_to_data()

        return self.render(data)
