"""AIS HTTP API routes for address standardization, geocoding, and City data lookups."""

from collections import OrderedDict
from functools import wraps
from itertools import chain

from flask import Response, make_response, redirect, request, url_for
from geoalchemy2.functions import ST_Transform
from geoalchemy2.shape import to_shape
from passyunk.parser import PassyunkParser
from sqlalchemy import desc, text

from ais import app, app_db as db, util
from ais.models import (
    Address,
    AddressSummary,
    AddressTag,
    DorParcel,
    ENGINE_SRID,
    Geocode,
    OpaAccountNumChanges,
    OpaProperty,
    PwdParcel,
    StreetIntersection,
    StreetSegment,
)
from ..util import NotNoneDict
from .errors import json_error
from .paginator import Paginator, QueryPaginator
from .serializers import (
    AddressJsonSerializer,
    IntersectionJsonSerializer,
    ServiceAreaSerializer,
)

config = app.config
OWNER_RESPONSE_LIMIT = config["OWNER_RESPONSE_LIMIT"]
DEFAULT_AIS_MAX_RANGE = config["DEFAULT_AIS_MAX_RANGE"]
_DEFAULT_PARSER = PassyunkParser()
_SA_YES_NO_LAYERS = [
    layer.get("layer_id", "")
    for layer in config["SERVICE_AREAS"]["layers"]
    if layer.get("value_method", "") == "yes_or_no"
]
_COORD_SRID_MAP = {"stateplane": 2272, "latlon": 4326}


# ---------------------------------------------------------------------------
# Shared response, query-arg, pagination, and tag helpers
# ---------------------------------------------------------------------------

def cache_for(hours=0, minutes=0, seconds=0):
    """Set Cache-Control max-age header on 2xx/3xx responses."""
    max_age = int(hours * 3600 + minutes * 60 + seconds)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            resp = make_response(fn(*args, **kwargs))
            if 200 <= resp.status_code < 400:
                resp.cache_control.public = True
                resp.cache_control.max_age = max_age
            return resp

        return wrapper

    return decorator


def json_response(*args, **kwargs):
    return Response(*args, mimetype="application/json", **kwargs)


def _error_response(status: int, message: str, details: dict | None = None):
    return json_response(response=json_error(status, message, details), status=status)


def _is_flag_enabled(args, name: str) -> bool:
    """Return True if query param `name` is present and not explicitly 'false'."""
    return name in args and args[name].lower() != "false"


def _get_srid(args):
    return args.get("srid") if "srid" in args else config["DEFAULT_API_SRID"]


def _build_crs(srid) -> dict:
    return {
        "type": "link",
        "properties": {
            "type": "proj4",
            "href": f"http://spatialreference.org/ref/epsg/{srid}/proj4/",
        },
    }


def _parse_query(query: str, max_range: int | None = None) -> dict:
    if max_range is None:
        return _DEFAULT_PARSER.parse(query)
    return PassyunkParser(MAX_RANGE=int(max_range)).parse(query)


def validate_page_param(req, paginator):
    """Parse and bounds-check the `page` query parameter."""
    page_str = req.args.get("page", "1")
    try:
        return paginator.validate_page_num(page_str), None
    except QueryPaginator.ValidationError as e:
        return None, json_error(404, e.message, e.data)


def get_tag_data(addresses_page):
    """Load AddressTag rows only for the addresses on the current page."""
    street_addresses = [address.street_address for address, _geocode_type, _geom in addresses_page]
    if not street_addresses:
        return {}
    tags = AddressTag.query.filter(AddressTag.street_address.in_(street_addresses)).all()
    all_tags: dict[str, dict[str, list]] = {}
    for tag in tags:
        all_tags.setdefault(tag.street_address, {}).setdefault(tag.key, []).append(tag)
    return all_tags


def _render_paginated_addresses(
    addresses_query,
    *,
    metadata: dict,
    not_found_message: str,
    not_found_details: dict,
    srid=None,
    include_crs: bool = True,
    serializer_kwargs: dict | None = None,
):
    """Paginate an AddressSummary query, fetch page tags, and serialize to GeoJSON."""
    paginator = QueryPaginator(addresses_query)
    if paginator.collection_size == 0:
        return _error_response(404, not_found_message, not_found_details)

    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    resolved_srid = srid if srid is not None else _get_srid(request.args)
    meta = dict(metadata)
    if include_crs:
        meta["crs"] = _build_crs(resolved_srid)

    addresses_page = list(paginator.get_page(page_num))
    all_tags = get_tag_data(addresses_page)

    serializer = AddressJsonSerializer(
        metadata=meta,
        pagination=paginator.get_page_info(page_num),
        srid=resolved_srid,
        tag_data=all_tags,
        **(serializer_kwargs or {}),
    )
    return json_response(response=serializer.serialize_many(addresses_page), status=200)


@app.errorhandler(404)
@app.errorhandler(500)
def handle_errors(e):
    code = getattr(e, "code", 500)
    description = getattr(e, "description", None)
    return _error_response(code, description, None)


# ---------------------------------------------------------------------------
# Address lookup & centerline cascade
# ---------------------------------------------------------------------------

@app.route("/unknown/<path:query>")
@cache_for(hours=1)
def unknown_cascade_view(**kwargs):
    """Estimate location and service areas by interpolating along a street centerline."""
    query = kwargs.get("query")
    normalized_address = kwargs.get("normalized_address")
    search_type = kwargs.get("search_type")
    parsed = kwargs.get("parsed")
    seg_id = parsed["components"]["cl_seg_id"]
    base_address = parsed["components"]["base_address"]
    centerline_offset = config["GEOCODE"]["centerline_offset"]
    centerline_end_buffer = config["GEOCODE"]["centerline_end_buffer"]

    address = Address(parsed)
    address.street_address = parsed["components"]["output_address"]
    address.street_code = parsed["components"]["street"]["street_code"]
    address.seg_id = seg_id
    address.usps_bldgfirm = parsed["components"]["mailing"]["bldgfirm"]
    address.usps_type = parsed["components"]["mailing"]["uspstype"]
    address.election_block_id = parsed["components"]["election"]["blockid"]
    address.election_precinct = parsed["components"]["election"]["precinct"]
    address.li_address_key = None
    address.pwd_account_nums = None
    address.li_parcel_id = None

    not_found_details = {
        "query": query,
        "normalized": normalized_address,
        "search_type": search_type,
    }
    if not seg_id:
        return _error_response(404, "Could not find any addresses matching query.", not_found_details)

    cascadedseg = StreetSegment.query.filter_by_seg_id(seg_id).first()
    if not cascadedseg:
        return _error_response(404, "Could not find any addresses matching query.", not_found_details)

    # Determine street side and interpolation range (prefer true_range over full centerline range)
    seg_side = "R" if cascadedseg.right_from % 2 == address.address_low % 2 and cascadedseg.right_to != 0 else "L"
    from_num, to_num = (
        (cascadedseg.right_from, cascadedseg.right_to)
        if seg_side == "R"
        else (cascadedseg.left_from, cascadedseg.left_to)
    )

    true_range_stmt = text("""
        SELECT true_left_from, true_left_to, true_right_from, true_right_to
        FROM true_range
        WHERE seg_id = :seg_id
    """)
    true_range_result = list(chain(*db.session.execute(true_range_stmt, {"seg_id": cascadedseg.seg_id}).fetchall()))

    if true_range_result and seg_side == "R" and true_range_result[3] is not None and true_range_result[2] is not None:
        side_delta = true_range_result[3] - true_range_result[2]
        cascade_geocode_type = "true_range"
    elif true_range_result and seg_side == "L" and true_range_result[1] is not None and true_range_result[0] is not None:
        side_delta = true_range_result[1] - true_range_result[0]
        cascade_geocode_type = "true_range"
    else:
        side_delta = to_num - from_num
        cascade_geocode_type = "full_range"

    distance_ratio = 0.5 if side_delta == 0 else (address.address_low - cascadedseg.right_from) / side_delta
    shape = to_shape(cascadedseg.geom)
    if to_num < address.address_low or from_num > address.address_low:
        cascade_geocode_type = "out_of_range"

    seg_xsect_xy = util.interpolate_buffered(shape, distance_ratio, centerline_end_buffer)
    seg_xy = util.offset(shape, seg_xsect_xy, centerline_offset, seg_side)

    sa_stmt = text("""
        WITH foo AS (
            SELECT layer_id, value
            FROM service_area_polygon
            WHERE ST_Intersects(geom, ST_SetSRID(ST_GeomFromText(:wkt), :srid))
        )
        SELECT DISTINCT ON (cols.layer_id) cols.layer_id, foo.value
        FROM service_area_layer cols
        LEFT JOIN foo ON foo.layer_id = cols.layer_id
    """)
    sa_data = OrderedDict(
        (item[0], item[1])
        for item in db.session.execute(sa_stmt, {"wkt": seg_xy.wkt, "srid": ENGINE_SRID}).fetchall()
    )

    paginator = Paginator((address,))
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    srid = _get_srid(request.args)
    serializer = AddressJsonSerializer(
        metadata={
            "search_type": search_type,
            "query": query,
            "normalized": normalized_address,
            "search_params": request.args,
            "crs": _build_crs(srid),
        },
        pagination=paginator.get_page_info(page_num),
        srid=srid,
        normalized_address=normalized_address,
        base_address=base_address,
        estimated=cascade_geocode_type,
        shape=seg_xy,
        sa_data=sa_data,
    )
    return json_response(response=serializer.serialize_many(paginator.get_page(page_num)), status=200)


@app.route("/addresses/<path:query>")
@cache_for(hours=1)
def addresses(query):
    """Look up standardized address components, geocodes, tags, and service areas."""
    query = query.strip("/")

    # Batch queries are deprecated; take only the first query before any semicolon
    if ";" in query:
        query = query[: query.index(";")]
    requestargs = {
        arg.split(";", 1)[0]: request.args.get(arg).split(";", 1)[0]
        for arg in request.args
    }

    max_range = requestargs.get("max_range", DEFAULT_AIS_MAX_RANGE)
    try:
        parsed = _parse_query(query, max_range=int(max_range))
        search_type = parsed["type"]
        normalized_address = parsed["components"]["output_address"]
    except Exception:
        return _error_response(
            404,
            "Could not parse query.",
            {"query": query, "normalized": "", "search_type": ""},
        )

    comps = parsed["components"]
    addr_comps = comps["address"]
    street_comps = comps["street"]
    unit_comps = comps["address_unit"]

    base_address = comps["base_address"]
    full_num = addr_comps["full"]
    low_num = addr_comps["low_num"]
    high_num_full = addr_comps["high_num_full"]
    high_num = addr_comps["high_num"]
    street_full = street_comps["full"]
    seg_id = comps["cl_seg_id"]
    cl_addr_match = comps["cl_addr_match"]
    unit_type = unit_comps["unit_type"]
    unit_num = unit_comps["unit_num"]

    addr_num = f"{low_num}-{high_num}" if high_num else low_num
    base_address_no_num_suffix = f"{addr_num} {street_full}"

    if search_type not in ("address", "street") or low_num is None:
        return _error_response(
            404,
            "Not a valid address.",
            {"query": query, "normalized": normalized_address, "search_type": search_type},
        )

    if seg_id and "RANGE:" not in cl_addr_match:
        loose_filters = OrderedDict([
            ("seg_id", seg_id),
            ("address_low", low_num if low_num is not None else full_num),
            ("address_low_suffix", addr_comps["addr_suffix"]),
            ("address_low_frac", addr_comps["fractional"]),
        ])
    else:
        loose_filters = OrderedDict([
            ("street_name", street_comps["name"]),
            ("address_low", low_num if low_num is not None else full_num),
            ("address_low_suffix", addr_comps["addr_suffix"]),
            ("address_low_frac", addr_comps["fractional"]),
            ("street_predir", street_comps["predir"]),
            ("street_postdir", street_comps["postdir"]),
            ("street_suffix", street_comps["suffix"]),
        ])

    filters = OrderedDict((k, v) for k, v in loose_filters.items() if v is not None)
    filters["address_high"] = high_num_full
    filters["unit_num"] = unit_num or ""
    if unit_num == "":
        filters["unit_type"] = unit_type or ""

    opa_only = _is_flag_enabled(request.args, "opa_only")
    include_units = _is_flag_enabled(request.args, "include_units")

    def query_addresses(f, u_type):
        return AddressSummary.query.filter_by(**f).filter_by_unit_type(u_type)

    def process_query(matched_query, match_type, *, ranged_fallback: bool, active_unit_type):
        matched_query = (
            matched_query.include_child_units(
                include_units,
                is_range=False if ranged_fallback else high_num_full is not None,
                is_unit=active_unit_type is not None,
                request=request,
            )
            .exclude_non_opa(opa_only)
            .get_address_geoms(request)
            .order_by_address()
        )

        if matched_query.first() is None:
            if opa_only:
                return _error_response(
                    404,
                    "Could not find any opa addresses matching the query.",
                    {"query": query, "normalized": normalized_address, "search_type": search_type},
                )
            return _error_response(
                404,
                "Invalid query.",
                {
                    "query": query,
                    "normalized": normalized_address,
                    "search_type": search_type,
                    "search_params": requestargs,
                },
            )

        try:
            return _render_paginated_addresses(
                matched_query,
                metadata={
                    "query": query,
                    "normalized": normalized_address,
                    "search_type": search_type,
                    "search_params": requestargs,
                },
                not_found_message="Could not find any opa addresses matching the query." if opa_only else "Invalid query.",
                not_found_details={
                    "query": query,
                    "normalized": normalized_address,
                    "search_type": search_type,
                    "search_params": requestargs,
                },
                serializer_kwargs={
                    "normalized_address": normalized_address,
                    "base_address": base_address,
                    "match_type": match_type,
                    "ref_addr": normalized_address,
                },
            )
        except Exception:
            return _error_response(
                404,
                "Invalid query.",
                {
                    "query": query,
                    "normalized": normalized_address,
                    "search_type": search_type,
                    "search_params": requestargs,
                },
            )

    # Progressive fallback chain: exact -> base -> base without suffix -> ranged low_num variants
    cur_unit_type = unit_type
    matched = query_addresses(filters, cur_unit_type)
    if matched.first():
        return process_query(matched, "exact", ranged_fallback=False, active_unit_type=cur_unit_type)

    if normalized_address != base_address:
        filters_copy = filters.copy()
        if "unit_num" in filters_copy:
            filters_copy["unit_num"] = ""
            cur_unit_type = None
        matched = query_addresses(filters_copy, cur_unit_type)
        if matched.first():
            return process_query(matched, "has_base", ranged_fallback=False, active_unit_type=cur_unit_type)

    if base_address != base_address_no_num_suffix:
        filters_copy = filters.copy()
        if "unit_num" in filters_copy:
            filters_copy["unit_num"] = ""
            cur_unit_type = None
        filters_copy.pop("address_low_suffix", None)
        filters_copy.pop("address_low_frac", None)
        matched = query_addresses(filters_copy, cur_unit_type)
        if matched.first():
            return process_query(matched, "has_base_no_suffix", ranged_fallback=False, active_unit_type=cur_unit_type)

    if high_num:
        filters_copy = filters.copy()
        filters_copy.pop("address_high", None)
        matched = query_addresses(filters_copy, cur_unit_type)
        if matched.first():
            return process_query(matched, "in_range", ranged_fallback=True, active_unit_type=cur_unit_type)

        if normalized_address != base_address:
            if "unit_num" in filters_copy:
                filters_copy["unit_num"] = ""
                cur_unit_type = None
            matched = query_addresses(filters_copy, cur_unit_type)
            if matched.first():
                return process_query(matched, "in_range_has_base", ranged_fallback=True, active_unit_type=cur_unit_type)

        if base_address != base_address_no_num_suffix:
            filters_copy.pop("address_low_suffix", None)
            filters_copy.pop("address_low_frac", None)
            matched = query_addresses(filters_copy, cur_unit_type)
            if matched.first():
                return process_query(matched, "in_range_has_base_no_suffix", ranged_fallback=True, active_unit_type=cur_unit_type)

    # No database match found: return 404 or cascade to centerline interpolation
    if opa_only:
        return _error_response(
            404,
            "Could not find any opa addresses matching the query.",
            {"query": query, "normalized": normalized_address, "search_type": search_type},
        )
    if request.args.get("estimate", "").lower() == "false":
        return _error_response(
            404,
            "Could not find any known addresses matching the query.",
            {"query": query, "normalized": normalized_address, "search_type": search_type},
        )
    return unknown_cascade_view(
        query=query,
        normalized_address=normalized_address,
        search_type=search_type,
        parsed=parsed,
    )


# ---------------------------------------------------------------------------
# Block, owner, account, and parcel endpoints
# ---------------------------------------------------------------------------

@app.route("/block/<path:query>")
@cache_for(hours=1)
def block(query):
    """Look up addresses within the 100-block containing the queried address."""
    query = query.strip("/")
    parsed = _parse_query(query)
    search_type = "block"
    normalized_address = parsed["components"]["output_address"]

    try:
        low_num = parsed["components"]["address"]["low_num"]
        address_num = int(low_num if low_num is not None else parsed["components"]["address"]["full"])
    except (TypeError, ValueError):
        return _error_response(
            404,
            "No valid block number provided.",
            {"query": query, "normalized": normalized_address, "search_type": search_type},
        )

    block_num = (address_num // 100) * 100
    street_comps = parsed["components"]["street"]
    filters = NotNoneDict(
        street_name=street_comps["name"],
        street_predir=street_comps["predir"],
        street_postdir=street_comps["postdir"],
        street_suffix=street_comps["suffix"],
    )
    opa_only = _is_flag_enabled(request.args, "opa_only")

    matched = (
        AddressSummary.query.filter_by(**filters)
        .filter(AddressSummary.address_low >= block_num)
        .filter(AddressSummary.address_low < block_num + 100)
        .exclude_children()
        .exclude_non_opa(opa_only)
        .get_address_geoms(request)
        .order_by_address()
    )

    msg = (
        "Could not find any opa addresses matching query."
        if opa_only
        else "Could not find any address on a block matching query."
    )
    return _render_paginated_addresses(
        matched,
        metadata={
            "search_type": search_type,
            "query": query,
            "normalized": normalized_address,
            "search_params": request.args,
        },
        not_found_message=msg,
        not_found_details={"query": query, "normalized": normalized_address, "search_type": search_type},
        include_crs=False,
        serializer_kwargs={"normalized_address": normalized_address},
    )


@app.route("/owner/<query>")
@cache_for(hours=1)
def owner(query):
    """Look up addresses owned by names containing all query tokens."""
    query = query.strip("/")
    owner_parts = query.upper().split()
    if len(query) < 2 or all(len(part) < 2 for part in owner_parts):
        return _error_response(404, "Query too short, please be more descriptive.", {"query": query})

    matched = (
        AddressSummary.query.filter_by_owner(*owner_parts)
        .exclude_non_opa(_is_flag_enabled(request.args, "opa_only"))
        .get_address_geoms(request)
        .order_by_owner_address(query)
        .limit(OWNER_RESPONSE_LIMIT)
    )
    return _render_paginated_addresses(
        matched,
        metadata={
            "search_type": "owner",
            "query": query,
            "normalized": owner_parts,
            "search_params": request.args,
        },
        not_found_message="Could not find any addresses with owner matching query.",
        not_found_details={"query": query},
    )


@app.route("/account/<query>")
@cache_for(hours=1)
def account(query):
    """Look up addresses by OPA account number (following historical account-number changes)."""
    query = query.strip("/")
    parsed = _parse_query(query)
    search_type = parsed["type"]
    normalized = parsed["components"]["output_address"]

    tagged_opa = OpaProperty.query.filter(OpaProperty.account_num == normalized).all()
    if not tagged_opa:
        changed = OpaAccountNumChanges.query.filter(
            OpaAccountNumChanges.old_opa_account_num == normalized
        ).all()
        if changed:
            new_nums = tuple({x.new_opa_account_num for x in changed})
            tagged_opa = OpaProperty.query.filter(OpaProperty.account_num.in_(new_nums)).all()

    street_addresses = tuple({x.street_address for x in tagged_opa})
    matched = (
        AddressSummary.query.filter(AddressSummary.street_address.in_(street_addresses))
        .exclude_non_opa(_is_flag_enabled(request.args, "opa_only"))
        .get_address_geoms(request)
        .order_by(desc(AddressSummary.street_address.in_(street_addresses)))
    )
    return _render_paginated_addresses(
        matched,
        metadata={
            "search_type": search_type,
            "query": query,
            "normalized": normalized,
            "search_params": request.args,
        },
        not_found_message="Could not find any addresses matching query.",
        not_found_details={"query": query, "search_type": search_type},
    )


@app.route("/pwd_parcel/<query>")
@cache_for(hours=1)
def pwd_parcel(query):
    """Look up addresses associated with a PWD parcel ID."""
    if not (query.isdigit() and len(query) < 8):
        return _error_response(404, "Not a valid pwd_parcel_id.", {"query": query})

    search_type = "pwd_parcel_id"
    include_units = _is_flag_enabled(request.args, "include_units")

    pwd_query = PwdParcel.query.filter(PwdParcel.parcel_id == query)
    if include_units:
        rows = (
            pwd_query.join(AddressSummary, AddressSummary.pwd_parcel_id == query)
            .add_columns(AddressSummary.street_address.label("address_summary_street_address"))
            .all()
        )
        street_addresses = tuple({r.address_summary_street_address for r in rows})
    else:
        street_addresses = tuple({r.street_address for r in pwd_query.all()})

    matched = (
        AddressSummary.query.filter(AddressSummary.street_address.in_(street_addresses))
        .exclude_non_opa(_is_flag_enabled(request.args, "opa_only"))
        .get_address_geoms(request)
        .order_by(desc(AddressSummary.street_address.in_(street_addresses)))
    )
    return _render_paginated_addresses(
        matched,
        metadata={
            "search_type": search_type,
            "query": query,
            "normalized": query,
            "search_params": request.args,
        },
        not_found_message="Could not find any addresses matching query.",
        not_found_details={"query": query, "search_type": search_type},
    )


@app.route("/dor_parcel/<query>")
@cache_for(hours=1)
def dor_parcel(query):
    """Look up addresses associated with a DOR MapReg parcel ID."""
    parsed = _parse_query(query)
    normalized_id = parsed["components"]["output_address"]
    search_type = parsed["type"]
    if search_type != "mapreg":
        return _error_response(404, "Not a valid dor_parcel_id.", {"query": query})

    street_addresses = tuple({
        x.street_address for x in DorParcel.query.filter(DorParcel.parcel_id == normalized_id).all()
    })
    matched = (
        AddressSummary.query.filter(AddressSummary.street_address.in_(street_addresses))
        .exclude_non_opa(_is_flag_enabled(request.args, "opa_only"))
        .get_address_geoms(request)
        .order_by(desc(AddressSummary.street_address.in_(street_addresses)))
    )
    return _render_paginated_addresses(
        matched,
        metadata={
            "search_type": search_type,
            "query": query,
            "normalized": normalized_id,
            "search_params": request.args,
        },
        not_found_message="Could not find any addresses matching query.",
        not_found_details={"query": query, "search_type": search_type},
    )


# ---------------------------------------------------------------------------
# Intersections, reverse geocoding, and service areas
# ---------------------------------------------------------------------------

@app.route("/intersection/<path:query>")
@cache_for(hours=1)
def intersection(query):
    """Look up a street intersection by street codes or street names."""
    query = query.strip("/")
    parsed = _parse_query(query)
    search_type = "intersection" if parsed["type"] == "intersection_addr" else parsed["type"]
    if search_type != "intersection":
        return _error_response(404, "Not a valid intersection query.", {"query": query})

    s1 = parsed["components"]["street"]
    s2 = parsed["components"]["street_2"]
    s1_code, s2_code = s1["street_code"], s2["street_code"]
    code_min = str(min(int(s1_code), int(s2_code))) if s1_code and s2_code else None
    code_max = str(max(int(s1_code), int(s2_code))) if s1_code and s2_code else None

    if code_min and code_max:
        intersections = StreetIntersection.query.filter_by(
            street_1_code=code_min, street_2_code=code_max
        ).order_by_intersection()
    else:
        filters = {
            "street_1_name": s1["name"],
            "street_2_name": s2["name"],
            **NotNoneDict(
                street_1_code=code_min,
                street_2_code=code_max,
                street_1_predir=s1["predir"],
                street_1_postdir=s1["postdir"],
                street_1_suffix=s1["suffix"],
                street_2_predir=s2["predir"],
                street_2_postdir=s2["postdir"],
                street_2_suffix=s2["suffix"],
            ),
        }
        intersections = StreetIntersection.query.filter_by(**filters)

    # Retry with street_1 and street_2 reversed if no match found
    if not intersections.first():
        rev_filters = {
            "street_1_name": s2["name"],
            "street_2_name": s1["name"],
            **NotNoneDict(
                street_2_code=code_min,
                street_1_code=code_max,
                street_1_predir=s2["predir"],
                street_1_postdir=s2["postdir"],
                street_1_suffix=s2["suffix"],
                street_2_predir=s1["predir"],
                street_2_postdir=s1["postdir"],
                street_2_suffix=s1["suffix"],
            ),
        }
        intersections = StreetIntersection.query.filter_by(**rev_filters)

    intersections = intersections.order_by_intersection().distinct(
        StreetIntersection.street_1_full, StreetIntersection.street_2_full
    )

    paginator = QueryPaginator(intersections)
    intersections_count = paginator.collection_size
    if intersections_count == 0:
        return _error_response(
            404,
            "Could not find intersection matching query.",
            {
                "query": query,
                "search_type": search_type,
                "normalized": {"street_name_1": s1["name"], "street_name_2": s2["name"]},
            },
        )

    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    srid = _get_srid(request.args)
    intersections_page = list(paginator.get_page(page_num))
    normalized = (
        f"{intersections_page[0].street_1_full} & {intersections_page[0].street_2_full}"
        if intersections_count == 1
        else f"{s1['full']} & {s2['full']}"
    )
    serializer = IntersectionJsonSerializer(
        metadata={
            "search_type": search_type,
            "query": query,
            "normalized": normalized,
            "search_params": request.args,
            "crs": _build_crs(srid),
        },
        pagination=paginator.get_page_info(page_num),
        srid=srid,
        match_type="exact",
    )
    return json_response(response=serializer.serialize_many(intersections_page), status=200)


@app.route("/reverse_geocode/<path:query>")
@cache_for(hours=1)
def reverse_geocode(query):
    """Find the nearest geocoded address to a lon/lat or PA State Plane coordinate pair."""
    query = query.strip("/")
    parsed = _parse_query(query)
    search_type = parsed["type"]
    normalized = parsed["components"]["output_address"]

    srid = _COORD_SRID_MAP.get(search_type)
    if srid is None:
        return _error_response(
            404,
            "Please format your query in State Plane or latitude longitude coordinates separated by a space or comma.",
            {"search_type": search_type, "query": query, "normalized": normalized},
        )

    x, y = normalized.split(",", 1)
    search_radius = min(
        int(request.args.get("search_radius", config["DEFAULT_SEARCH_RADIUS"])),
        config["MAXIMUM_SEARCH_RADIUS"],
    )

    reverse_geocode_stmt = text("""
        SELECT street_address, geocode_type
        FROM geocode
        WHERE ST_DWithin(geom, ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :srid), :engine_srid), :search_radius)
          AND geocode_type IN (7, 8, 5)
        ORDER BY
            geom <-> ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :srid), :engine_srid),
            length(street_address) ASC
        LIMIT 1
    """)
    row = db.session.execute(
        reverse_geocode_stmt,
        {
            "x": float(x),
            "y": float(y),
            "srid": int(srid),
            "engine_srid": int(ENGINE_SRID),
            "search_radius": int(search_radius),
        },
    ).first()

    if not row:
        return _error_response(
            404,
            "Could not find any addresses matching query.",
            {"query": query, "normalized": normalized, "search_type": search_type},
        )

    street_address, geocode_type = row
    parsed_addr = _parse_query(street_address)
    comps = parsed_addr["components"]
    unit_type = comps["address_unit"]["unit_type"]
    unit_num = comps["address_unit"]["unit_num"]
    high_num = comps["address"]["high_num_full"]
    low_num = comps["address"]["low_num"]

    filters = {
        "address_high": high_num,
        "unit_num": unit_num or "",
        **NotNoneDict(
            street_name=comps["street"]["name"],
            address_low=low_num if low_num is not None else comps["address"]["full"],
            address_low_suffix=comps["address"]["addr_suffix"],
            address_low_frac=comps["address"]["fractional"],
            street_predir=comps["street"]["predir"],
            street_postdir=comps["street"]["postdir"],
            street_suffix=comps["street"]["suffix"],
        ),
    }
    if unit_num == "":
        filters["unit_type"] = unit_type or ""

    matched = (
        AddressSummary.query.filter_by(**filters)
        .filter_by_unit_type(unit_type)
        .include_child_units(
            _is_flag_enabled(request.args, "include_units"),
            is_range=high_num is not None,
            is_unit=unit_type is not None,
            request=request,
        )
        .outerjoin(Geocode, Geocode.street_address == AddressSummary.street_address)
        .filter(Geocode.geocode_type == geocode_type)
        .add_columns(Geocode.geocode_type, ST_Transform(Geocode.geom, srid))
        .exclude_non_opa(_is_flag_enabled(request.args, "opa_only"))
        .order_by_address()
    )

    return _render_paginated_addresses(
        matched,
        metadata={
            "search_type": "coordinates",
            "query": query,
            "normalized": normalized,
            "search_params": request.args,
        },
        not_found_message="Could not find any addresses matching query.",
        not_found_details={"search_type": search_type, "query": query, "normalized": normalized},
        srid=srid,
        serializer_kwargs={
            "normalized_address": comps["output_address"],
            "base_address": comps["base_address"],
            "match_type": "nearest",
        },
    )


@app.route("/service_areas/<path:query>")
@cache_for(hours=1)
def service_areas(query):
    """Return all service areas intersecting a lon/lat or State Plane coordinate pair."""
    query = query.strip("/")
    parsed = _parse_query(query)
    search_type = parsed["type"]

    if search_type == "none":
        return _error_response(404, "There are no intersecting service areas.", {"query": query})

    srid = _COORD_SRID_MAP.get(search_type)
    if srid is None:
        return _error_response(404, "Not a valid service_area query.", {"query": query, "search_type": search_type})

    normalized = parsed["components"]["output_address"]
    x, y = normalized.split(",", 1)
    coords = [float(x), float(y)]

    sa_stmt = text("""
        WITH foo AS (
            SELECT layer_id,
                CASE WHEN layer_id = ANY(:yes_no_layers) THEN
                    CASE WHEN trim(coalesce(value, '')) != '' THEN 'Yes' ELSE 'No' END
                ELSE value
                END AS value
            FROM service_area_polygon
            WHERE ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :srid), :engine_srid))
        )
        SELECT DISTINCT ON (cols.layer_id) cols.layer_id, foo.value
        FROM service_area_layer cols
        LEFT JOIN foo ON foo.layer_id = cols.layer_id
        UNION
        (
            SELECT 'nearest_seg'::text AS layer_id, cast(ss.seg_id AS text) AS value
            FROM street_segment ss
            ORDER BY st_distance(ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :srid), :engine_srid), ss.geom) ASC
            LIMIT 1
        )
        ORDER BY layer_id
    """)
    sa_data = OrderedDict(
        (item[0], item[1])
        for item in db.session.execute(
            sa_stmt,
            {
                "x": coords[0],
                "y": coords[1],
                "srid": int(srid),
                "engine_srid": int(ENGINE_SRID),
                "yes_no_layers": _SA_YES_NO_LAYERS,
            },
        ).fetchall()
    )

    if all(value is None for value in sa_data.values()):
        return _error_response(
            404,
            "There are no intersecting service areas.",
            {"search_type": search_type, "query": query, "normalized": normalized},
        )

    serializer = ServiceAreaSerializer(
        metadata={
            "search_type": "coordinates",
            "query": query,
            "search_params": request.args,
            "normalized": normalized,
            "crs": _build_crs(srid),
        },
        sa_data=sa_data,
        coordinates=coords,
    )
    return json_response(response=serializer.serialize(), status=200)


# ---------------------------------------------------------------------------
# Unified search router, landing redirect, and health check
# ---------------------------------------------------------------------------

_PARSER_SEARCH_TYPE_MAP = {
    "address": addresses,
    "intersection_addr": intersection,
    "opa_account": account,
    "mapreg": dor_parcel,
    "block": block,
    "latlon": reverse_geocode,
    "stateplane": reverse_geocode,
    "street": addresses,
}


@app.route("/search/<path:query>")
@cache_for(hours=1)
def search(query):
    """Unified search endpoint dispatching to address, intersection, parcel, account, block, or reverse geocode."""
    query = query.strip("/")

    entry_length = len(query) + sum(len(arg) for arg in request.args)
    if entry_length >= 80:
        return _error_response(404, "Query exceeds character limit.", {"query": query})

    if ";" in query:
        query = query[: query.index(";")]

    try:
        parsed = _parse_query(query)
    except Exception:
        return _error_response(404, "Could not parse query.", {"query": query})

    search_type = parsed["type"]
    normalized_address = parsed["components"]["output_address"]

    if search_type != "none":
        try:
            return _PARSER_SEARCH_TYPE_MAP[search_type](query)
        except Exception:
            return _error_response(
                404,
                "Invalid query.",
                {"query": query, "normalized": normalized_address, "search_type": search_type},
            )

    if query.isdigit() and len(query) < 8:
        return pwd_parcel(query)
    return _error_response(404, "Query not recognized.", {"query": query})


@app.route("/")
def base_landing():
    return redirect(url_for("base_landing", _external=True) + "index.html", code=302)


@app.route("/api/health-check")
def health():
    try:
        db.session.execute(text("SELECT 1 FROM geocode LIMIT 1")).fetchall()
        return "All okay!", 200
    except Exception:
        return "DB failure!", 504
