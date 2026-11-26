"""GeoJSON serializers for addresses, intersections, and service area queries."""

from collections import OrderedDict
from collections.abc import Iterable
import json

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping

from ais import app, util
from ais.models import Address, ENGINE_SRID

config = app.config
_TAG_FIELD_MAP = {
    tag["tag_key"]: tag["name"] for tag in config["ADDRESS_SUMMARY"]["tag_fields"]
}
_GEOCODE_PRIORITY_BY_CODE = {
    code: name for name, code in config["ADDRESS_SUMMARY"]["geocode_priority"].items()
}

_SEARCH_TYPE_MATCH_MAP = {
    "block": "on block",
    "owner": "contains query string",
    "coordinates": "exact location",
    "stateplane": "exact location",
    "mapreg": "exact_key",
    "pwd_parcel_id": "exact_key",
    "opa_account": "exact_key",
}


class BaseSerializer:
    def model_to_data(self, instance):
        raise NotImplementedError()

    def render(self, data):
        raise NotImplementedError()

    def serialize(self, instance):
        return self.render(self.model_to_data(instance))

    def serialize_many(self, instances):
        return self.render([self.model_to_data(instance) for instance in instances])


class GeoJSONSerializer(BaseSerializer):
    def __init__(self, metadata=None, pagination=None, srid=4326):
        self.metadata = metadata
        self.pagination = pagination
        self.srid = srid
        super().__init__()

    def geom_to_shape(self, geom):
        return util.geom_to_shape(geom, from_srid=ENGINE_SRID, to_srid=self.srid)

    def project_shape(self, shape):
        return util.project_shape(shape, from_srid=ENGINE_SRID, to_srid=self.srid)

    def shape_to_geodict(self, shape):
        data = mapping(shape) if shape else {"type": "Point", "coordinates": [None, None]}
        return OrderedDict([
            ("type", data["type"]),
            ("coordinates", data["coordinates"]),
        ])

    def render(self, data):
        final_data = []
        if self.metadata:
            final_data += sorted(self.metadata.items(), reverse=True)

        if isinstance(data, list):
            if self.pagination:
                final_data += self.pagination.items()
            final_data += [
                ("type", "FeatureCollection"),
                ("features", data),
            ]
        else:
            final_data += data.items()

        return json.dumps(OrderedDict(final_data))

    def get_address_response_relationships(self, address=None, **_kwargs):
        """Classify the relationship (`match_type`) between a returned address and the queried ref address."""
        ref_address = Address(self.ref_addr)
        address = Address(address.street_address)
        ref_base_address = " ".join([ref_address.address_full, ref_address.street_full])
        ref_base_address_no_suffix = f"{ref_address.address_full_num} {ref_address.street_full}"
        base_address = " ".join([address.address_full, address.street_full])
        base_address_no_suffix = f"{address.address_full_num} {address.street_full}"
        unit_type_variations = ("APT", "UNIT", "#")
        street_address_variations = (
            [
                address.street_address,
                address.street_address.replace(address.unit_type, "APT"),
                address.street_address.replace(address.unit_type, "UNIT"),
                address.street_address.replace(address.unit_type, "#"),
            ]
            if address.unit_type
            else []
        )

        if address.street_address == ref_address.street_address:
            return self.match_type

        if address.unit_type not in ("", None):
            if address.address_high is None:
                if ref_address.unit_type not in ("", None):
                    if ref_address.unit_num == address.unit_num:
                        if ref_address.unit_type == address.unit_type:
                            return "exact" if not ref_address.address_high else "in_range"
                        if ref_address.unit_type in unit_type_variations and address.unit_type in unit_type_variations:
                            return "generic_unit_sibling" if not ref_address.address_high else "in_range_generic_unit_sibling"
                        return "unit_sibling" if not ref_address.address_high else "in_range_unit_sibling"
                    if base_address == ref_base_address:
                        return "has_base_unit_child"
                    if base_address_no_suffix == ref_base_address_no_suffix:
                        return "has_base_no_suffix_unit_child"
                    if ref_address.address_high:
                        if ref_address.address_low_suffix == address.address_low_suffix:
                            if address.unit_num == ref_address.unit_num:
                                return "in_range"
                            if not address.unit_num:
                                return "has_base_in_range"
                            return "has_base_in_range_unit_child"
                        if address.address_low_suffix:
                            return (
                                "has_base_no_suffix_in_range_suffix_child_unit_child"
                                if ref_address.address_low_suffix
                                else "has_base_in_range"
                            )
                        return (
                            "has_base_no_suffix_in_range_unit_child"
                            if ref_address.address_low_suffix
                            else "has_base_in_range_unit_child"
                        )
                    return None
                if ref_address.address_high is not None:
                    if ref_address.address_low_suffix == address.address_low_suffix:
                        return "in_range_unit_child"
                    if ref_address.address_low_suffix:
                        return (
                            "has_base_no_suffix_in_range_suffix_child_unit_child"
                            if address.address_low_suffix
                            else "has_base_no_suffix_in_range_unit_child"
                        )
                    return "in_range_suffix_child_unit_child"
                if address.address_low_suffix is not None and address.base_address_no_suffix == ref_address.base_address:
                    return "has_base_no_suffix_unit_child"
                return "unit_child"

            # Ranged unit address
            if ref_address.unit_type is not None:
                if ref_address.street_address in street_address_variations:
                    return "generic_unit_sibling"
                if ref_address.address_high is None:
                    if ref_address.unit_type in unit_type_variations and address.unit_type in unit_type_variations:
                        return "range_parent_unit_sibling"
                    return "range_parent_unit_child"
                return (
                    "unit_sibling"
                    if ref_address.address_low == address.address_low and ref_address.address_high == address.address_high
                    else "overlapping_unit_sibling"
                )
            return "range_parent_unit_child" if ref_address.address_high is None else "unit_child"

        # Non-unit address
        if address.address_high:
            if not ref_address.address_high:
                return "range_parent"
            if ref_address.address_high != address.address_high or ref_address.address_low != address.address_low:
                if not ref_address.unit_type and ref_address.address_low_suffix == address.address_low_suffix:
                    return "overlaps"
                if ref_base_address == base_address:
                    return "has_base_overlaps"
                return "overlapping_suffix_child" if address.address_low_suffix else "has_base_no_suffix_overlaps"
            return "has_base" if ref_address.address_low_suffix == address.address_low_suffix else "has_base_no_suffix"

        if ref_address.address_high:
            if ref_address.unit_type:
                if ref_address.address_low_suffix == address.address_low_suffix:
                    return "in_range" if not ref_address.unit_num else "has_base_in_range"
                if address.address_low_suffix:
                    return (
                        "in_range_suffix_child"
                        if not ref_address.address_low_suffix
                        else "has_base_no_suffix_in_range_suffix_child"
                    )
                return "has_base_no_suffix_in_range"
            if ref_address.address_low_suffix == address.address_low_suffix:
                return "in_range" if not ref_address.unit_num else "in_range_unit_sibling"
            if address.address_low_suffix:
                return "in_range_suffix_child"
            return "has_base_no_suffix_in_range"

        if ref_address.base_address == address.street_address:
            return "has_base"
        if ref_address.base_address_no_suffix == address.street_address:
            return "has_base_no_suffix"
        if address.base_address_no_suffix == ref_address.base_address:
            return "has_base_suffix_child"
        if address.base_address_no_suffix == ref_address.base_address_no_suffix:
            return "has_base_no_suffix_suffix_child"
        return "has_base"


class AddressJsonSerializer(GeoJSONSerializer):
    excluded_tags = set(config["ADDRESS_SUMMARY"]["non_summary_and_api_tags"])

    def __init__(
        self,
        ref_addr=None,
        tag_data=None,
        geom_type=None,
        geom_source=None,
        normalized_address=None,
        base_address=None,
        shape=None,
        sa_data=None,
        estimated=None,
        match_type=None,
        **kwargs,
    ):
        self.geom_type = geom_type
        self.geom_source = geom_source
        self.normalized_address = normalized_address
        self.base_address = base_address
        self.shape = shape
        self.estimated = estimated
        self.sa_data = sa_data
        self.match_type = match_type
        self.tag_data = tag_data
        self.ref_addr = ref_addr
        super().__init__(**kwargs)

    def transform_tag_data(self, tag_data, address):
        """Format address tags either as source-detail lists or pipe-delimited strings."""
        if not tag_data:
            return None

        addr_tags = tag_data.get(address.street_address)
        if not addr_tags:
            return None

        render_source = OrderedDict()
        source_details = "source_details" in self.metadata.get("search_params", {})

        for key, tag_values in addr_tags.items():
            sorted_vals = sorted(tag_values, key=lambda v: v.value)
            if source_details:
                render_source[key] = [
                    {
                        "source": val.linked_path if val.linked_path else address.street_address,
                        "value": val.value,
                    }
                    for val in sorted_vals
                ]
            else:
                render_source[key] = "|".join(val.value for val in sorted_vals)

        return render_source

    def transform_exceptions(self, data):
        """Apply field-specific response formatting (diversion rate & multi-value lists)."""
        props = data["properties"]
        try:
            props["recycling_diversion_rate"] = round(float(props["recycling_diversion_rate"]) / 100, 3)
        except (KeyError, TypeError, ValueError):
            pass

        if "source_details" not in self.metadata.get("search_params", {}):
            for list_field in ("opa_owners", "pwd_account_nums", "zoning_document_ids"):
                val = props[list_field]
                props[list_field] = val.split("|") if val else []

        return data

    def model_to_data(self, address):
        shape = self.project_shape(self.shape) if self.shape else None
        geocode_response_type = None
        geom = None

        if isinstance(address, Iterable) and not self.estimated:
            address, geocode_response_type, geom = address
            if geocode_response_type is None:
                geocode_response_type = 99
            geocode_response_type = _GEOCODE_PRIORITY_BY_CODE[geocode_response_type]

        if geocode_response_type:
            geom_type_name = geocode_response_type
        elif not self.estimated:
            geom_type_name = address.geocode_type
        else:
            geom_type_name = self.estimated

        if self.estimated != "parsed":
            shape = self.geom_to_shape(geom) if shape is None else shape
            geom_data = self.shape_to_geodict(shape)
            geom_data["geocode_type"] = geom_type_name
            geom_data.move_to_end("geocode_type", last=False)

            sa_data = OrderedDict()
            if not self.estimated:
                for col in address.service_areas.__table__.columns:
                    if col.name in ("id", "street_address", "zip_code"):
                        continue
                    sa_data[col.name] = getattr(address.service_areas, col.name)
            else:
                sa_data = self.sa_data
                sa_data["zip_code"] = address.zip_code if address.zip_code else sa_data["zip_code"]

            search_type = self.metadata["search_type"]
            if search_type in ("address", "street"):
                match_type = (
                    self.get_address_response_relationships(address=address, ref_addr=self.ref_addr)
                    if not self.estimated
                    else "unmatched"
                )
            elif search_type == "opa_account" and self.metadata["normalized"] != address.opa_account_num:
                match_type = "changed_key"
            else:
                match_type = _SEARCH_TYPE_MATCH_MAP[search_type]
        else:
            match_type = self.estimated
            geom_data = {"geocode_type": None, "type": None, "coordinates": None}
            sa_data = {}

        data = OrderedDict([
            ("type", "Feature"),
            ("ais_feature_type", "address"),
            ("match_type", match_type or None),
            ("properties", OrderedDict([
                ("street_address", address.street_address),
                ("base_address", address.base_address),
                ("address_low", address.address_low),
                ("address_low_suffix", address.address_low_suffix),
                ("address_low_frac", address.address_low_frac),
                ("address_high", address.address_high),
                ("street_predir", address.street_predir),
                ("street_name", address.street_name),
                ("street_suffix", address.street_suffix),
                ("street_postdir", address.street_postdir),
                ("unit_type", address.unit_type),
                ("unit_num", address.unit_num),
                ("floor", address.floor),
                ("street_full", address.street_full),
                ("street_code", address.street_code),
                ("seg_id", address.seg_id),
                ("zip_code", address.zip_code),
                ("zip_4", address.zip_4),
                ("usps_bldgfirm", address.usps_bldgfirm),
                ("usps_type", address.usps_type),
                ("election_block_id", address.election_block_id),
                ("election_precinct", address.election_precinct),
                ("pwd_parcel_id", ""),
                ("dor_parcel_id", ""),
                ("li_address_key", ""),
                ("eclipse_location_id", ""),
                ("bin", ""),
                ("li_parcel_id", address.li_parcel_id or ""),
                ("zoning_document_ids", ""),
                ("pwd_account_nums", ""),
                ("opa_account_num", ""),
                ("opa_owners", ""),
                ("opa_address", ""),
                ("legacy_certificate_of_occupancy_permit_nums", ""),
                ("legacy_certificate_of_use_and_occupancy_permit_nums", ""),
            ])),
            ("geometry", geom_data),
        ])

        rendered_tags = self.transform_tag_data(self.tag_data, address)
        if rendered_tags:
            for key, val in rendered_tags.items():
                if key in self.excluded_tags:
                    continue
                data["properties"][_TAG_FIELD_MAP[key]] = val

        data["properties"].update(sa_data)
        return self.transform_exceptions(data)


class IntersectionJsonSerializer(GeoJSONSerializer):
    def __init__(self, match_type=None, **kwargs):
        self.match_type = match_type
        super().__init__(**kwargs)

    def model_to_data(self, intersection):
        if intersection.geom is not None:
            shape = self.project_shape(to_shape(intersection.geom))
            geom_data = self.shape_to_geodict(shape)
            geom_data["geocode_type"] = "intersection"
        else:
            geom_data = OrderedDict([
                ("geocode_type", None),
                ("type", None),
                ("coordinates", None),
            ])

        return OrderedDict([
            ("type", "Feature"),
            ("ais_feature_type", "intersection"),
            ("match_type", self.match_type),
            ("street_address", f"{intersection.street_1_full} & {intersection.street_2_full}"),
            ("properties", OrderedDict([
                ("int_id", intersection.int_id),
                ("street_1", OrderedDict([
                    ("street_code", intersection.street_1_code),
                    ("street_full", intersection.street_1_full),
                    ("street_name", intersection.street_1_name),
                    ("street_predir", intersection.street_1_predir),
                    ("street_postdir", intersection.street_1_postdir),
                    ("street_suffix", intersection.street_1_suffix),
                ])),
                ("street_2", OrderedDict([
                    ("street_code", intersection.street_2_code),
                    ("street_full", intersection.street_2_full),
                    ("street_name", intersection.street_2_name),
                    ("street_predir", intersection.street_2_predir),
                    ("street_postdir", intersection.street_2_postdir),
                    ("street_suffix", intersection.street_2_suffix),
                ])),
            ])),
            ("geometry", geom_data),
        ])


class ServiceAreaSerializer:
    def __init__(self, coordinates=None, sa_data=None, metadata=None, **_kwargs):
        self.coordinates = coordinates
        self.sa_data = sa_data
        self.metadata = metadata

    def transform_exceptions(self, data):
        sa = data["service_areas"]
        try:
            sa["recycling_diversion_rate"] = round(float(sa["recycling_diversion_rate"]) / 100, 3)
            sa["nearest_seg"] = int(sa["nearest_seg"])
        except (KeyError, TypeError, ValueError):
            pass

        for key, val in sa.items():
            sa[key] = val if val else ""
        return data

    def render(self, data):
        final_data = []
        if self.metadata:
            final_data += sorted(self.metadata.items(), reverse=True)
        final_data += data.items()

        result = OrderedDict(final_data)
        result["geometry"] = OrderedDict([
            ("geocode_type", "input"),
            ("type", "Point"),
            ("coordinates", self.coordinates),
        ])
        return json.dumps(result)

    def serialize(self):
        data = {**self.metadata, "service_areas": self.sa_data}
        return self.render(self.transform_exceptions(data))
