"""
Does three primary things:
* Geocoding lat/lng to addresses
* Standardizing addresses
* Providing identifiers for other systems
"""

from ais import app
from ais.models import Address, AddressProperty, AddressSummary, AddressLink
from flask import Response, request
from passyunk.parser import PassyunkParser

from .errors import json_error
from .paginator import QueryPaginator
from .serializers import AddressJsonSerializer
from ..util import NotNoneDict


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


@app.route('/addresses/<path:query>')
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
    all_queries = list(filter(bool, (q.strip() for q in query.split(';'))))
    all_parsed = [PassyunkParser().parse(q) for q in all_queries]

    # Match a set of addresses. Filters will either be loose, where an omission
    # is ignored, or scrict, where an omission is treated as an explicit NULL.
    # For example, if the street_predir is omitted, then we should still match
    # all addresses that match the rest of the information; this is a loose
    # filter. However, if we do not provide an address_high, we should assume
    # that we're not looking for a ranged address; this is a strict filter.
    all_addresses = None

    for parsed in all_parsed:
        unit_type = parsed['components']['unit']['unit_type']
        unit_num = parsed['components']['unit']['unit_num']
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
            unit_num=unit_num if unit_num or not unit_type else '',
        )

        addresses = AddressSummary.query\
            .filter_by(**loose_filters, **strict_filters)\
            .filter_by_unit_type(unit_type)\
            .include_child_units(
                'include_units' in request.args,
                is_range=high_num is not None,
                is_unit=unit_type is not None)\
            .exclude_non_opa('opa_only' in request.args)

        if all_addresses is None:
            all_addresses = addresses
        else:
            all_addresses = all_addresses.union(addresses)

    all_addresses = all_addresses.order_by_address()
    paginator = QueryPaginator(all_addresses)

    # Ensure that we have results
    normalized_addresses = [parsed['components']['street_address'] for parsed in all_parsed]
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
        metadata={'query': query, 'normalized': normalized_addresses},
        pagination=paginator.get_page_info(page_num))
    result = serializer.serialize_many(addresses_page)
    return json_response(response=result, status=200)

    # TODO: If it's not a perfect match, do we want to do something like a
    # soundex or some other fuzzy match?


@app.route('/block/<path:query>')
def block_view(query):
    """
    Looks up information about the 100-range that the given address falls
    within.

    TODO: Consider matching the segment ID and finding the low and high. This
          would be instead of hardcoding a low of 0 and high of 100. Maybe this
          would go at a new route, like `segment` or `block-face`.
    """
    parsed = PassyunkParser().parse(query)
    normalized_address = parsed['components']['street_address']

    # Ensure that we can get a valid address number
    try:
        address_num = int(parsed['components']['address']['low_num']
                          if parsed['components']['address']['low_num'] is not None
                          else parsed['components']['address']['full'])
    except ValueError:
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
        .exclude_non_opa('opa_only' in request.args)\
        .order_by_address()
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
        pagination=paginator.get_page_info(page_num))
    result = serializer.serialize_many(block_page)
    return json_response(response=result, status=200)


@app.route('/owner/<query>')
def owner(query):
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
        pagination=paginator.get_page_info(page_num))
    result = serializer.serialize_many(page)
    return json_response(response=result, status=200)


@app.route('/account/<number>')
def account_number_view(number):
    """
    Looks up information about the property with the given OPA account number.
    Should only ever return one or zero corresponding addresses.
    """
    address = AddressSummary.query\
        .filter(AddressSummary.opa_account_num==number)\
        .exclude_non_opa('opa_only' in request.args)\
        .order_by_address()\
        .first()

    # Make sure we found a property
    if address is None:
        error = json_error(404, 'Could not find property with account number.',
                           {'number': number})
        return json_response(response=error, status=404)

    # Render the response
    serializer = AddressJsonSerializer()
    result = serializer.serialize(address)
    return json_response(response=result, status=200)
