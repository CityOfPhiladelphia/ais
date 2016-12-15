import json
from collections import OrderedDict
from ais import util, models
from geoalchemy2.shape import to_shape
from geoalchemy2.functions import ST_X, ST_Y
from shapely import wkt
from ais import app, app_db as db
config = app.config
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
            #print(0)
            # Base query response address (not joined with flag(s))
            for link_address in link_addresses:
                match_type = None
                related_address = {}
                address_1 = link_address['address_1']
                address_2 = link_address['address_2']
                relationship = link_address['relationship']

                if address_1 == street_address:
                    #print(1, link_address)
                    match_type = query_address_1_match_map[relationship]
                    #related_address[link_address['address_2']] = relationship

                elif address_2 == street_address:
                    #print(2, link_address)
                    if street_address == self.base_address:
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

                if address_1 == street_address:
                    #print(5, link_address)
                    match_type = unit_address_1_match_map[relationship]
                    related_address[link_address['address_2']] = query_address_2_match_map[relationship]
                    #related_addresses.append(related_address)
                elif address_2 == base_address and street_address != self.normalized_address:
                    #print(6, link_address)
                    related_address[link_address['address_1']] = unit_address_2_match_map[relationship]
                    #related_addresses.append(related_address)

        return match_type#, related_addresses


class AddressJsonSerializer (GeoJSONSerializer):
    excluded_tags = ('info_resident', 'info_company', 'voter_name')

    def __init__(self, geom_type=None, geom_source=None, in_street=False, normalized_address=None, base_address=None, shape=None, pcomps=None, sa_data=None, estimated=None, **kwargs):
        #self.geom_type = kwargs.get('geom_type') if 'geom_type' in kwargs else None
        self.geom_type = geom_type
        #self.geom_source = kwargs.get('geom_source') if 'geom_source' in kwargs else None
        self.geom_source = geom_source
        #self.in_street = True if kwargs.get('in_street') == True else False
        self.in_street = in_street
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

        from collections import Iterable

        shape = self.project_shape(self.shape) if self.shape else None
        geocode_response_type = None
        # Handle instances where query includes request arg 'parcel_geocode_location' which joins geom from geocode,
        # creating an iterable object

        geom = None
        if isinstance(address, Iterable) and not self.estimated:
            # for i in address:
            #     print(i)

            address, geocode_response_type, geom = address
            gp_map = config['ADDRESS_SUMMARY']['geocode_priority']
            geocode_response_type = (list(gp_map.keys())[list(gp_map.values()).index(geocode_response_type)])  # Prints george

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
            match_type = self.get_address_link_relationships(address.street_address, self.base_address) if not self.estimated else 'estimated'
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
                ('zip_code', address.zip_code or None),
                ('zip_4', address.zip_4 if address.zip_4 and address.zip_4.isdigit() and len(address.zip_4) == 4 else ''),
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
        #data['properties'].update({'related_addresses': related_addresses})

        data = self.transform_exceptions(data)

        return data


class IntersectionJsonSerializer (GeoJSONSerializer):

    def __init__(self, geom_type='centroid', geom_source=None, estimated=None, **kwargs):
        #self.geom_type = 'Point'
        #self.geom_source = geom_source
        self.estimated = estimated
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

            cascade_geocode_type = self.estimated['cascade_geocode_type'] if self.estimated and self.estimated[
                'cascade_geocode_type'] else None
            geom_type = {'geocode_type': 'choose one point of intersection'}
            geom_data.update(geom_type)
            match_type = 'exact'
        else:
            geom_data = OrderedDict([
                ('geocode_type', None),
                ('type', None),
                ('coordinates', None)
            ])
            match_type = self.estimated['cascade_geocode_type']

        # Build the intersection feature, then attach properties
        #num_ints = intersection.int_ids.count('|') + 1
        data = OrderedDict([
            ('type', 'Feature'),
            ('ais_feature_type', 'intersection'),
            ('match_type', match_type),
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
