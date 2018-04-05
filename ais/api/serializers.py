import json
from collections import OrderedDict, Iterable
from geoalchemy2.shape import to_shape
from ais import app, util #, app_db as db
from ais.models import Address, ENGINE_SRID
#from itertools import chain

config = app.config
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


    def get_address_response_relationships(self, address=None, **kwargs):
        # TODO: assign in include_units fct?

        #print("normalized: ", self.normalized_address)
        #print(self.ref_addr)
        ref_address = Address(self.ref_addr)
        address = Address(address.street_address)
        # print(ref_address, address)
        ref_base_address = ' '.join([ref_address.address_full, ref_address.street_full])
        ref_base_address_no_suffix = '{} {}'.format(ref_address.address_full_num, ref_address.street_full)
        base_address = ' '.join([address.address_full, address.street_full])
        base_address_no_suffix = '{} {}'.format(address.address_full_num, address.street_full)
        match_type = None
        unit_type_variations = ["APT", "UNIT", "#"]
        street_address_variations = [address.street_address,
                                     address.street_address.replace(address.unit_type, "APT"),
                                     address.street_address.replace(address.unit_type, "UNIT"),
                                     address.street_address.replace(address.unit_type, "#")] if address.unit_type else []

        #print(address.unit_type, ref_address.unit_type)
        if address.street_address == ref_address.street_address:
            # Address is same as reference address
            match_type = self.match_type
        # elif address.base_address == ref_address.base_address:
        #     # 1769 FRANKFORD AVE UNIT 99
        #     match_type = 'has_base'
        # elif address.base_address_no_suffix == ref_address.base_address or address.base_address == ref_address.base_address_no_suffix:
        #     #6037 N 17TH ST #A or 6037B N 17TH ST #A
        #     match_type = 'has_base_no_suffix'
        elif address.unit_type not in ('', None):
            # Address is different from ref address and has unit type
            if address.address_high is None:
                # Address also doesn't have a high num
                if ref_address.unit_type not in ('', None):
                    # Reference address has unit type
                    if ref_address.unit_num == address.unit_num:
                        if ref_address.unit_type == address.unit_type:
                            match_type = 'exact' if not ref_address.address_high else 'in_range'
                        # Reference and address have same unit num
                        elif all(unit_type in unit_type_variations for unit_type in [ref_address.unit_type, address.unit_type]):
                            match_type = 'generic_unit_sibling' if not ref_address.address_high else 'in_range_generic_unit_sibling'
                        else:
                            match_type = 'unit_sibling' if not ref_address.address_high else 'in_range_unit_sibling'
                    elif base_address == ref_base_address:
                        match_type = 'has_base_unit_child'
                    elif base_address_no_suffix == ref_base_address_no_suffix:
                        match_type = 'has_base_no_suffix_unit_child'
                    elif ref_address.address_high:
                        if ref_address.address_low_suffix == address.address_low_suffix:
                            if address.unit_num == ref_address.unit_num:
                                match_type = 'in_range'
                            elif not address.unit_num:
                                match_type = 'has_base_in_range'
                            else:
                                # 1769-71 FRANKFORD AVE UNIT 8?include_units
                                match_type = 'has_base_in_range_unit_child'
                        elif address.address_low_suffix:
                            if ref_address.address_low_suffix:
                                match_type = 'has_base_no_suffix_in_range_suffix_child_unit_child'
                            else:
                                match_type = 'has_base_in_range'
                        else:
                            if ref_address.address_low_suffix:
                                match_type = 'has_base_no_suffix_in_range_unit_child'
                            else:
                                match_type = 'has_base_in_range_unit_child'
                elif ref_address.address_high is not None:
                    # Ref address has no unit type but has high_num:
                    if ref_address.address_low_suffix == address.address_low_suffix:
                        match_type = 'in_range_unit_child'
                    elif ref_address.address_low_suffix:
                        if address.address_low_suffix:
                            match_type = 'has_base_no_suffix_in_range_suffix_child_unit_child'
                        else:
                            match_type = 'has_base_no_suffix_in_range_unit_child'
                    else:
                        match_type = 'in_range_suffix_child_unit_child'

                else:
                    # ref address has no unit type or address high num
                    if address.address_low_suffix is not None and address.base_address_no_suffix == ref_address.base_address:
                        match_type = 'has_base_no_suffix_unit_child'
                    else:
                        match_type = 'unit_child'
            else:
                # Address is different from ref address and has unit type and high num (is ranged unit address)
                if ref_address.unit_type is not None:
                    # Unit type is a generic unit type
                    if ref_address.street_address in street_address_variations:
                        match_type = 'generic_unit_sibling'
                    else:
                        if ref_address.address_high is None:
                            if all(unit_type in unit_type_variations for unit_type in [ref_address.unit_type, address.unit_type]):
                                match_type = 'range_parent_unit_sibling'
                            else:
                                match_type = 'range_parent_unit_child'
                        else:
                            match_type = 'unit_sibling' if ref_address.address_low == address.address_low and ref_address.address_high == address.address_high else 'overlapping_unit_sibling'
                else:
                    if ref_address.address_high is None:
                        match_type = 'range_parent_unit_child'
                    else:
                        match_type = 'unit_child'
                    # match_type = 'range_parent'
        else:
            # Address is different from ref address but has no unit type
            if address.address_high:
                if not ref_address.address_high:
                    match_type = 'range_parent'
                else:
                    if ref_address.address_high != address.address_high or ref_address.address_low != address.address_low:
                        if not ref_address.unit_type and ref_address.address_low_suffix == address.address_low_suffix:
                            match_type = 'overlaps'
                        elif ref_base_address == base_address:
                            match_type =  'has_base_overlaps'
                        else:
                            if address.address_low_suffix:
                                # 4923-49 N 16TH ST
                                match_type = 'overlapping_suffix_child'
                            else:
                                match_type = 'has_base_no_suffix_overlaps'
                    else:
                        if ref_address.address_low_suffix == address.address_low_suffix:
                            match_type = 'has_base'
                        else:
                            # 4923-47 N 16TH ST
                            match_type = 'has_base_no_suffix'
            elif ref_address.address_high:
                # no address.address_high but ref_address.address_high
                if ref_address.unit_type:
                    if ref_address.address_low_suffix == address.address_low_suffix:
                        if not ref_address.unit_num:
                            match_type = 'in_range'
                        else:
                            # 902A-4 N 3RD ST UNIT 2
                            match_type = 'has_base_in_range'

                    elif address.address_low_suffix:
                        # 902-4 N 3RD ST UNIT 2
                        if not ref_address.address_low_suffix:
                            match_type = 'in_range_suffix_child'
                        else:
                            match_type = 'has_base_no_suffix_in_range_suffix_child'
                    else:
                        # 902R-4 N 3RD ST UNIT 2
                        match_type = 'has_base_no_suffix_in_range'
                else:
                    if ref_address.address_low_suffix == address.address_low_suffix:
                        if not ref_address.unit_num:
                            # 901A-4 N 3RD ST
                            match_type = 'in_range'
                        else:
                            match_type = 'in_range_unit_sibling'
                    elif address.address_low_suffix:
                        # 902-4 N 3RD ST UNIT 2
                        match_type = 'in_range_suffix_child'
                    else:
                        # 902R-4 N 3RD ST
                        match_type = 'has_base_no_suffix_in_range'
            elif ref_address.base_address == address.street_address:
                # 1769 FRANKFORD AVE UNIT 8
                match_type = 'has_base'
            elif ref_address.base_address_no_suffix == address.street_address:
                # 1769R FRANKFORD AVE
                match_type = 'has_base_no_suffix'
            elif address.base_address_no_suffix == ref_address.base_address:
                # 902 N 3RD ST UNIT 2
                match_type = 'has_base_suffix_child'
            elif address.base_address_no_suffix == ref_address.base_address_no_suffix:
                # 902 N 3RD ST UNIT 2
                match_type = 'has_base_no_suffix_suffix_child'
            else:
                match_type = 'has_base'

        return match_type


class AddressJsonSerializer (GeoJSONSerializer):
    excluded_tags = ('info_resident', 'info_company', 'voter_name')

    def __init__(self, ref_addr=None, tag_data=None, geom_type=None, geom_source=None, normalized_address=None, base_address=None, shape=None, sa_data=None, estimated=None, match_type=None, **kwargs):
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
        self.ref_addr = ref_addr

        super().__init__(**kwargs)

    def geom_to_shape(self, geom):
        return util.geom_to_shape(
            geom, from_srid=ENGINE_SRID, to_srid=self.srid)

    def project_shape(self, shape):
        return util.project_shape(
            shape, from_srid=ENGINE_SRID, to_srid=self.srid)

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
        render_source = OrderedDict()
        if not tag_data:
            return data_comps
        # If 'source_details' query flag, then return tags as lists of dicts with source and value
        if 'source_details' in self.metadata.get('search_params'):
            for key in tag_data[address.street_address]:
                if not key in render_source:
                    render_source[key] = []
                for val in tag_data[address.street_address].get(key):
                    render_source[key].append({'source': val.linked_path if val.linked_path else address.street_address, 'value': val.value})
            data_comps.append(render_source)
        # If no 'source_details' in request args return tags as key (pipe delimited) value pairs
        else:
            try:
                for key in tag_data[address.street_address]:
                    if not key in render_source:
                        render_source[key] = None
                    for val in tag_data[address.street_address].get(key):
                        render_source[key] = render_source[key] + '|' + val.value if render_source[key] else val.value
                        # render_source[key] = [render_source[key], val.value] if render_source[key] else val.value
                data_comps.append(render_source)
            except:
                pass
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
        opa_owners = data['properties']['opa_owners']
        pwd_account_nums = data['properties']['pwd_account_nums']
        zoning_document_ids = data['properties']['zoning_document_ids']
        if not 'source_details' in self.metadata.get('search_params'):
            data['properties']['opa_owners'] = opa_owners.split("|") if opa_owners else []
            data['properties']['pwd_account_nums'] = pwd_account_nums.split("|") if pwd_account_nums else []
            data['properties']['zoning_document_ids'] = zoning_document_ids.split("|") if zoning_document_ids else []

        return data

    def model_to_data(self, address):
        # print(address)

        shape = self.project_shape(self.shape) if self.shape else None
        geocode_response_type = None
        # Handle instances where query includes request arg 'parcel_geocode_location' which joins geom from geocode,
        # creating an iterable object
        geom = None
        if isinstance(address, Iterable) and not self.estimated:
            # print(address)
            # print(len(address))
            address, geocode_response_type, geom = address
            gp_map = config['ADDRESS_SUMMARY']['geocode_priority']
            geocode_response_type = (list(gp_map.keys())[list(gp_map.values()).index(geocode_response_type)])

        #cascade_geocode_type = self.estimated if self.estimated else None
        geom_type = {'geocode_type': geocode_response_type} if geocode_response_type else {'geocode_type': address.geocode_type} \
            if not self.estimated else {'geocode_type': self.estimated}

        if self.estimated != 'parsed':
            shape = self.geom_to_shape(geom) if not shape else shape
            geom_data = self.shape_to_geodict(shape)
            geom_data.update(geom_type)
            geom_data.move_to_end('geocode_type', last=False)

            # Build the set of associated service areas
            sa_data = OrderedDict()
            if not self.estimated:
                #print(address.street_address, address.service_areas)
                for col in address.service_areas.__table__.columns:
                    if col.name in ('id', 'street_address'):
                        continue
                    sa_data[col.name] = getattr(address.service_areas, col.name)
            else:
                sa_data = self.sa_data
            # if self.metadata['search_type'] == 'address':
            if self.metadata['search_type'] in ('address', 'street', 'landmark'):
                match_type = self.get_address_response_relationships(address=address, ref_addr=self.ref_addr) if not self.estimated else 'unmatched'
            else:
                match_type_key = {
                    'block': 'on block',
                    'owner': 'contains query string',
                    'coordinates': 'exact location',
                    'stateplane': 'exact location',
                    'mapreg': 'exact_key',
                    'pwd_parcel_id': 'exact_key',
                    'opa_account': 'exact_key'
                }
                match_type = match_type_key[self.metadata['search_type']]

        else:
            match_type = self.estimated
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
                ('zip_code', address.zip_code),
                ('zip_4', address.zip_4),
                ('usps_bldgfirm', address.usps_bldgfirm),
                ('usps_type', address.usps_type),
                ('election_block_id', address.election_block_id),
                ('election_precinct', address.election_precinct),
                ('pwd_parcel_id', ''),
                ('dor_parcel_id', ''),
                ('li_address_key', ''),
                ('eclipse_location_id', ''),
                ('bin', ''),
                ('zoning_document_ids', ''),
                ('pwd_account_nums', ''),
                ('opa_account_num', ''),
                ('opa_owners', ''),
                ('opa_address', ''),
            ])),
            ('geometry', geom_data),
        ])

        data_comps = self.transform_tag_data(data, self.tag_data, address)
        if data_comps:
            for key, val in data_comps[0].items():
                if key in self.excluded_tags:
                    continue
                key_name = tag_field_map[key]
                data['properties'][key_name] = val

        data['properties'].update(sa_data)
        data = self.transform_exceptions(data)

        return data


class IntersectionJsonSerializer (GeoJSONSerializer):

    def __init__(self, match_type=None, **kwargs):
        self.match_type = match_type
        super().__init__(**kwargs)

    def geom_to_shape(self, geom):
        return util.geom_to_shape(
            geom, from_srid=ENGINE_SRID, to_srid=self.srid)

    def project_shape(self, shape):
        return util.project_shape(
            shape, from_srid=ENGINE_SRID, to_srid=self.srid)

    def shape_to_geodict(self, shape):
        from shapely.geometry import mapping
        data = mapping(shape)
        return OrderedDict([
            ('type', data['type']),
            ('coordinates', data['coordinates'])
        ])

    def model_to_data(self, intersection):

        if intersection.geom is not None:
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
            ('street_address', intersection.street_1_full + ' & ' + intersection.street_2_full),
            ('properties', OrderedDict([
                ('int_id', intersection.int_id),
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

    def __init__(self, coordinates=None, sa_data=None, metadata=None, seg_id=None, **kwargs):
        #self.seg_id = seg_id
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
            data['service_areas']['nearest_seg'] = int(data['service_areas']['nearest_seg'])

        except:
            pass
        # Change all nulls to empty strings:
        for key, val in data['service_areas'].items():
            val = val if val else ''
            data['service_areas'][key] = val

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
        #print("tag_data: ", tag_data)
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
                ('eclipse_location_id', {'source': '', 'value': ''}),
                ('bin', {'source': '', 'value': ''}),
                ('zoning_document_ids', {'source': '', 'value': ''}),
                ('pwd_account_nums', {'source': '', 'value': ''}),
                ('opa_account_num', {'source': '', 'value': ''}),
                ('opa_owners', {'source': '', 'value': ''}),
                ('opa_address', {'source': '', 'value': ''}),
            ])),
            ('geometry', {}),
        ])

        #data['properties'].update(sa_data)
        data.update(self.metadata)
        #print(self.tag_data)
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
