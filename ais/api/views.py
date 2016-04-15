"""
Does three primary things:
* Geocoding lat/lng to addresses
* Standardizing addresses
* Providing identifiers for other systems
"""

from ais import app
from ais.models import Address
from flask import Response
from passyunk.parser import PassyunkParser

from .errors import json_error
from .serializers import AddressJsonSerializer


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

    TODO: Filter for the actual pieces, not the whole address string :(. E.g.,
          "615 48TH ST" should resolve to "615 S 48TH ST".

    For geogode types:
    * PWD
    * DOR
    * True Range
    * Curb
    """
    parsed = PassyunkParser().parse(query)

    # Match a set of addresses
    std_address = parsed['components']['street_address']
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

    if addresses.count() == 0:
        error = json_error(404, 'Could not find addresses matching query.',
                           {'query': query, 'standardized': std_address})
        return Response(response=error, status=404,
                        mimetype="application/json")

    else:
        serializer = AddressJsonSerializer()
        result = serializer.serialize_many(addresses)
        return Response(response=result, status=200,
                        mimetype="application/json")

    # TODO: If it's not a perfect match, do we want to do something like a
    # soundex or some other fuzzy match?