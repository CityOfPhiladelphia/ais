"""
Does three primary things:
* Geocoding lat/lng to addresses
* Standardizing addresses
* Providing identifiers for other systems
"""

from ais import app
from ais.models import Address, AddressProperty, AddressSummary, AddressLink, StreetIntersection
from flask import Response, request
from flask_cachecontrol import cache_for
from passyunk.parser import PassyunkParser

from .errors import json_error
from .paginator import QueryPaginator
from .serializers import AddressJsonSerializer, IntersectionJsonSerializer
from ..util import NotNoneDict
import re

default_srid = 4326
# parser_search_type_map = {
#     'address': 'addresses_view',
#     'intersection_addr': 'intersection',
#     'opa_account': 'account_number_view',
#     'mapreg': 'dor_parcel'
# }


def json_response(*args, **kwargs):
    return Response(*args, mimetype='application/json', **kwargs)


def validate_page_param(request, paginator):
    page_str = request.args.get('page', '1')

    try:
        page_num = paginator.validate_page_num(page_str)
    except QueryPaginator.ValidationError as e:
        error = json_error(400, e.message, e.data)
        return None, error

    return page_num, None


@app.errorhandler(404)
@app.errorhandler(500)
def handle_errors(e):
    code = getattr(e, 'code', 500)
    description = getattr(e, 'description', None)
    error = json_error(code, description, None)
    return json_response(response=error, status=code)


@app.route('/addresses/<path:query>')
@cache_for(hours=1)
def addresses_view(query):
    """
    Looks up information about the address given in the query. Response is an
    object with the information for the matching address. The object includes:
    * A standardized, unambiguous address string
    * Address components
    * OPA #
    * DOR "ID"
    * L&I Key
    * Zoning something or other

    TODO: Give each address a score every time someone accesses it. This can be
          used for semi-intelligent ordering. For example, if I query for "440
          Broad St", I'll most often mean the school district building. However,
          with default ordering, a building on S Broad with a whole bunch of
          units comes up first. That's annoying. But if 440 N Broad was accessed
          a bunch of times, it should have a higher popularity score than any
          one of those units, and that should help it to the top of the list.

    TODO: Allow paginator to use skip/limit semantics instead of or in addition
          to page. Maybe allow one of page or skip but not both.

    TODO: Need a way to only return addresses that have OPA numbers. Filters?

    """
    query = query.strip('/')

    # Batch queries have been depreciated for this endpoint; handle first query of batch query attempts:
    requestargs = {}
    if ';' in query:
        query = query[:query.index(';')]
    for arg in request.args:
        val = request.args.get(arg)
        if ';' in arg:
            arg = arg[:arg.index(';')]
        if ';' in val:
            val = val[:val.index(';')]
        requestargs[arg] = val

    parsed = PassyunkParser().parse(query)
    search_type = parsed['type']

    # Match a set of addresses. Filters will either be loose, where an omission
    # is ignored, or scrict, where an omission is treated as an explicit NULL.
    # For example, if the street_predir is omitted, then we should still match
    # all addresses that match the rest of the information; this is a loose
    # filter. However, if we do not provide an address_high, we should assume
    # that we're not looking for a ranged address; this is a strict filter.

    unit_type = parsed['components']['address_unit']['unit_type']
    unit_num = parsed['components']['address_unit']['unit_num']
    high_num = parsed['components']['address']['high_num_full']
    low_num = parsed['components']['address']['low_num']

    loose_filters = NotNoneDict(
        street_name=parsed['components']['street']['name'],
        address_low=low_num if low_num is not None
            else parsed['components']['address']['full'],
        address_low_suffix=parsed['components']['address']['addr_suffix'],
        address_low_frac=parsed['components']['address']['fractional'],
        street_predir=parsed['components']['street']['predir'],
        street_postdir=parsed['components']['street']['postdir'],
        street_suffix=parsed['components']['street']['suffix'],
    )
    strict_filters = dict(
        address_high=high_num,
        # unit_num=unit_num if unit_num or not unit_type else '',
        unit_num=unit_num or '',
        # unit_type=unit_type or '',
    )

    filters = strict_filters.copy()
    filters.update(loose_filters)

    addresses = AddressSummary.query \
        .filter_by(**filters) \
        .filter_by_unit_type(unit_type) \
        .include_child_units(
            'include_units' in request.args,
            is_range=high_num is not None,
            is_unit=unit_type is not None) \
        .exclude_non_opa('opa_only' in request.args)

    addresses = addresses.order_by_address()
    paginator = QueryPaginator(addresses)

    # Ensure that we have results
    normalized_addresses = parsed['components']['output_address']
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find addresses matching query.',
                           {'query': query, 'normalized': normalized_addresses})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Render the response
    addresses_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'search type': search_type, 'query': query, 'normalized': normalized_addresses},
        pagination=paginator.get_page_info(page_num),
        srid=requestargs.get('srid') if 'srid' in request.args else default_srid,
        in_street='in_street' in requestargs)

    result = serializer.serialize_many(addresses_page)
    return json_response(response=result, status=200)

    # TODO: If it's not a perfect match, do we want to do something like a
    # soundex or some other fuzzy match?


@app.route('/block/<path:query>')
@cache_for(hours=1)
def block_view(query):
    """
    Looks up information about the 100-range that the given address falls
    within.

    TODO: Consider matching the segment ID and finding the low and high. This
          would be instead of hardcoding a low of 0 and high of 100. Maybe this
          would go at a new route, like `segment` or `block-face`.
    """
    query = query.strip('/')

    parsed = PassyunkParser().parse(query)
    normalized_address = parsed['components']['output_address']

    # Ensure that we can get a valid address number
    try:
        address_num = int(parsed['components']['address']['low_num']
                          if parsed['components']['address']['low_num'] is not None
                          else parsed['components']['address']['full'])
    except (TypeError, ValueError):
        error = json_error(400, 'No valid block number provided.',
                           {'query': query, 'normalized': normalized_address})
        return json_response(response=error, status=400)

    # Match a set of addresses
    block_num = ((address_num // 100) * 100)
    filters = NotNoneDict(
        street_name=parsed['components']['street']['name'],
        street_predir=parsed['components']['street']['predir'],
        street_postdir=parsed['components']['street']['postdir'],
        street_suffix=parsed['components']['street']['suffix'],
    )
    addresses = AddressSummary.query\
        .filter_by(**filters)\
        .filter(AddressSummary.address_low >= block_num)\
        .filter(AddressSummary.address_low < block_num + 100)\
        .exclude_children()\
        .exclude_non_opa('opa_only' in request.args)

    addresses = addresses.order_by_address()
    paginator = QueryPaginator(addresses)

    # Ensure that we have results
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find any address on a block matching query.',
                           {'query': query, 'normalized': normalized_address})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Render the response
    block_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'query': query, 'normalized': normalized_address},
        pagination=paginator.get_page_info(page_num),
        srid=request.args.get('srid') if 'srid' in request.args else default_srid)
    result = serializer.serialize_many(block_page)
    return json_response(response=result, status=200)


@app.route('/owner/<query>')
@cache_for(hours=1)
def owner(query):
    query = query.strip('/')

    owner_parts = query.upper().split()

    # Match a set of addresses
    addresses = AddressSummary.query\
        .filter_by_owner(*owner_parts)\
        .exclude_non_opa('opa_only' in request.args)\
        .order_by_address()

    paginator = QueryPaginator(addresses)

    # Ensure that we have results
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find any addresses with owner matching query.',
                           {'query': query})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Render the response
    page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'query': query, 'parsed': owner_parts},
        pagination=paginator.get_page_info(page_num),
        srid=request.args.get('srid') if 'srid' in request.args else default_srid)
    result = serializer.serialize_many(page)
    return json_response(response=result, status=200)


@app.route('/account/<number>')
@cache_for(hours=1)
def account_number_view(number):
    """
    Looks up information about the property with the given OPA account number.
    Returns all addresses with opa_account_num matching query.
    """
    addresses = AddressSummary.query\
        .filter(AddressSummary.opa_account_num==number)\
        .exclude_non_opa('opa_only' in request.args)\
        .order_by_address()

    paginator = QueryPaginator(addresses)

    #normalized_addresses = parsed['components']['output_address']

    # Ensure that we have results
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find addresses matching query.',
                           {'query': number})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Render the response
    addresses_page = paginator.get_page(page_num)

    # Serialize the response
    serializer = AddressJsonSerializer(
        metadata={'query': number},
        pagination=paginator.get_page_info(page_num),
        srid=request.args.get('srid') if 'srid' in request.args else default_srid
    )
    result = serializer.serialize_many(addresses_page)
    return json_response(response=result, status=200)


@app.route('/pwd_parcel/<id>')
@cache_for(hours=1)
def pwd_parcel(id):
    """
    Looks up information about the property with the given PWD parcel id.
    """
    addresses = AddressSummary.query\
        .filter(AddressSummary.pwd_parcel_id==id) \
        .exclude_non_opa('opa_only' in request.args) \
        .order_by_address()

    addresses = addresses.order_by_address()
    paginator = QueryPaginator(addresses)

    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find addresses matching query.',
                           {'query': id})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Serialize the response
    addresses_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'query': id},
        pagination=paginator.get_page_info(page_num),
        srid=request.args.get('srid') if 'srid' in request.args else default_srid
    )
    result = serializer.serialize_many(addresses_page)
    return json_response(response=result, status=200)


@app.route('/dor_parcel/<id>')
@cache_for(hours=1)
def dor_parcel(id):
    """
    Looks up information about the property with the given DOR parcel id.
    """
    normalized_id = id.replace('-', '') if '-' in id and id.index('-') == 6 else id

    addresses = AddressSummary.query\
        .filter(AddressSummary.dor_parcel_id==normalized_id) \
        .exclude_non_opa('opa_only' in request.args) \
        .order_by_address()

    addresses = addresses.order_by_address()
    paginator = QueryPaginator(addresses)

    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find addresses matching query.',
                           {'query': id})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Render the response
    addresses_page = paginator.get_page(page_num)

    # Render the response
    serializer = AddressJsonSerializer(
        metadata={'query': id},
        pagination=paginator.get_page_info(page_num),
        srid=request.args.get('srid') if 'srid' in request.args else default_srid
    )
    result = serializer.serialize_many(addresses_page)
    return json_response(response=result, status=200)


@app.route('/intersection/<path:query>')
@cache_for(hours=1)
def intersection(query):
    '''
    Called by search endpoint if search_type == "intersection_addr"
    '''
    query_original = query
    query = query.strip('/')
    arg_len = 0
    for arg in request.args:
        arg_len += len(arg)

    if len(query) + arg_len < 60:
        parsed = PassyunkParser().parse(query)
        search_type = parsed['type']

    street_1_full = parsed['components']['street']['full']
    street_1_name = parsed['components']['street']['name']
    street_1_code = parsed['components']['street']['street_code']
    street_2_full = parsed['components']['street_2']['full']
    street_2_name = parsed['components']['street_2']['name']
    street_2_code = parsed['components']['street_2']['street_code']
    street_code_min = str(min(int(street_1_code), int(street_2_code))) if street_1_code and street_2_code else ''
    street_code_max = str(max(int(street_1_code), int(street_2_code))) if street_1_code and street_2_code else ''

    strict_filters = dict(
        street_1_code=street_code_min,
        street_2_code=street_code_max,
    )
    filters = strict_filters.copy()
    intersections = StreetIntersection.query \
        .filter_by(**filters) \
        .order_by_intersection() \
        .choose_one()

    if not intersections:
        error = json_error(404, 'Could not find any intersection matching query.',
                           {'query': query_original, 'normalized': {'name_1': street_1_name, 'name_2': street_2_name}})
        return json_response(response=error, status=200)

    serializer = IntersectionJsonSerializer(
        metadata={'search type': search_type, 'query': query, 'normalized': [street_1_full + ' & ' + street_2_full, ]},
        srid=request.args.get('srid') if 'srid' in request.args else default_srid)
    result = serializer.serialize_many(intersections)

    return json_response(response=result, status=200)


@app.route('/search/<path:query>')
@cache_for(hours=1)
def search_view(query):

    """
    API Endpoint for various types of geocoding (not solely addresses)
    TODO: Implement batch geocoding endpoint
    """
    query_original = query
    query = query.strip('/')

    # Limit queries to < 60 characters total:
    arg_len = 0
    for arg in request.args:
        arg_len += len(arg)
    if len(query) + arg_len < 60:

        # We are not supporting batch queries, so if attempted only take first query
        query = query[:query.index(';')] if ';' in query else query

        parser_search_type_map = {
            'address': addresses_view,
            'intersection_addr': intersection,
            'opa_account': account_number_view,
            'mapreg': dor_parcel,
            'block': block_view,
        }

        parsed = PassyunkParser().parse(query)
        search_type = parsed['type']

        # get the corresponding view function
        view = parser_search_type_map[search_type]
        # call it
        return view(query)

    else:
        error = json_error(400, 'Query exceeds character limit.',
                           {'query': query})
        return json_response(response=error, status=404)
