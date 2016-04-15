"""
Does three primary things:
* Geocoding lat/lng to addresses
* Standardizing addresses
* Providing identifiers for other systems
"""

from ais import app
from ais.models import Address
from flask import Response, request
from passyunk.parser import PassyunkParser

from .errors import json_error
from .paginator import Paginator
from .serializers import AddressJsonSerializer


def json_response(*args, **kwargs):
    return Response(*args, mimetype='application/json', **kwargs)


@app.route('/addresses/<query>')
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

    TODO: Geocode addresses by matching against types in the following order:
          * PWD
          * DOR
          * True Range
          * Curb

    TODO: Give each address a score every time someone accesses it. This can be
          used for semi-intelligent ordering. For example, if I query for "440
          Broad St", I'll most often mean the school district building. However,
          with default ordering, a building on S Broad with a whole bunch of
          units comes up first. That's annoying. But if 440 N Broad was accessed
          a bunch of times, it should have a higher popularity score than any
          one of those units, and that should help it to the top of the list.

    TODO: Addresses should also have a match score that raises those addresses
          that match proportionally more filter criteria. For example, "1234
          Market St" matches the building as well as a number of units. The
          building should come first, since it's a more complete match for our
          query (less unmatched extant data than the other addresses).
    """
    parsed = PassyunkParser().parse(query)

    # Match a set of addresses
    filters = {
        key: value
        for key, value in (
            ('street_name', parsed['components']['street']['name']),
            ('address_low', parsed['components']['address']['low'] or parsed['components']['address']['full']),
            ('address_high', parsed['components']['address']['high']),
            ('street_predir', parsed['components']['street']['predir']),
            ('street_postdir', parsed['components']['street']['postdir']),
            ('street_suffix', parsed['components']['street']['suffix']),
            ('unit_num', parsed['components']['unit']['unit_num']),
            ('unit_type', parsed['components']['unit']['unit_type']),
        )
        if value is not None
    }
    addresses = Address.query.filter_by(**filters)
    paginator = Paginator(addresses)

    # Ensure that we have results
    normalized_address = parsed['components']['street_address']
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find addresses matching query.',
                           {'query': query, 'normalized': normalized_address})
        return json_response(response=error, status=404)

    # Figure out which page the user is requesting
    try:
        page_str = request.args.get('page', '1')
        page = int(page_str)
    except ValueError:
        error = json_error(400, 'Invalid page value.', {'page': page_str})
        return json_response(response=error, status=400)

    # Page has to be less than the available number of pages
    page_count = paginator.page_count
    if page < 1 or page > page_count:
        error = json_error(400, 'Page out of range.',
                           {'page': page, 'page_count': page_count})
        return json_response(response=error, status=400)

    # Render the response
    addresses_page = paginator.get_page(page)
    serializer = AddressJsonSerializer(
        metadata={'query': query, 'normalized': normalized_address},
        pagination=paginator.get_page_info(page))
    result = serializer.serialize_many(addresses_page)
    return json_response(response=result, status=200)

    # TODO: If it's not a perfect match, do we want to do something like a
    # soundex or some other fuzzy match?