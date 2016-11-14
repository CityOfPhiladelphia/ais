import json
from collections import OrderedDict
from ais import util, models


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
            final_data += self.metadata.items()

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


class AddressJsonSerializer (GeoJSONSerializer):
    excluded_tags = ('info_resident', 'info_company', 'voter_name')

    def __init__(self, geom_type='centroid', geom_source=None, **kwargs):
        self.geom_type = geom_type
        self.geom_source = geom_source
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
        # # TODO: Remove the following when street_code lives directly in the
        # # address_summary table.
        # address, street_code = address
        # address.street_code = street_code

        # Build the set of associated service areas
        sa_data = OrderedDict()
        for col in address.service_areas.__table__.columns:
            if col.name in ('id', 'street_address'):
                continue
            sa_data[col.name] = getattr(address.service_areas, col.name)

        if address.geocode_type:
            from shapely.geometry import Point
            shape = Point(address.geocode_x, address.geocode_y)
            shape = self.project_shape(shape)
            geom_data = self.shape_to_geodict(shape)
        else:
            geom_data = None

        # Build the address feature, then attach tags and service areas
        data = OrderedDict([
            ('type', 'Feature'),
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

                ('geom_type', 'centroid' if address.geocode_type else None),
                ('geom_source', address.geocode_type),
            ])),
            ('geometry', geom_data),
        ])

        data['properties'].update(sa_data)

        data = self.transform_exceptions(data)

        return data


class AddressSummaryJsonSerializer (GeoJSONSerializer):
    def model_to_data(self, address):
        data = OrderedDict([
            ('type', 'Feature'),
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

                ('zip_code', address.zip_code),
                ('zip_4', address.zip_4),

                ('seg_id', address.seg_id),
                ('seg_side', address.seg_side),
                ('pwd_parcel_id', address.pwd_parcel_id),
                ('dor_parcel_id', address.dor_parcel_id),
                ('opa_account_num', address.opa_account_num),
                ('opa_owners', address.opa_owners),
                ('opa_address', address.opa_address),
                ('info_residents', address.info_residents),
                ('info_companies', address.info_companies),
                ('pwd_account_nums', address.pwd_account_nums),
                ('li_address_key', address.li_address_key),
                ('voters', address.voters),

                ('geocode_type', address.geocode_type),
                ('geocode_x', address.geocode_x),
                ('geocode_y', address.geocode_y),
            ])),
            ('geometry', OrderedDict([
                ('type', 'Point'),
                ('coordinates', [address.geocode_x, address.geocode_y]),
            ])),
        ])
        return data

class IntersectionJsonSerializer (GeoJSONSerializer):

    def __init__(self, geom_type='centroid', geom_source=None, **kwargs):
        self.geom_type = geom_type
        self.geom_source = geom_source
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


    def model_to_data(self, streetintersection):

        if streetintersection.geocode_type:
            from shapely.geometry import Point
            shape = Point(streetintersection.geocode_x, streetintersection.geocode_y)
            shape = self.project_shape(shape)
            geom_data = self.shape_to_geodict(shape)
        else:
            geom_data = None

        # Build the intersection feature, then attach properties
        data = OrderedDict([
            ('type', 'Feature'),
            ('properties', OrderedDict([
                #('street_name_1', streetintersection.street_code_1),
                #('street_full_name_1', streetintersection.address_low),
                ('street_code_1', streetintersection.street_code_1),
                ('street_code_2', streetintersection.street_code_2),

                ('geom_type', 'centroid' if streetintersection.geocode_type else None),
                ('geom_source', streetintersection.geocode_type),
            ])),
            ('geometry', geom_data),
        ])

        data = self.transform_exceptions(data)

        return data