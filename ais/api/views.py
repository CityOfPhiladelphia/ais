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


@app.route('/address/<query>')
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
    """
    parsed = PassyunkParser().parse(query)
    std_address = parsed['components']['street_address']

    address = Address.query.filter_by(street_address=std_address).first()
    if address is None:
        error = json_error(404, 'Could not find address matching query.',
                           {'query': query, 'standardized': std_address})
        return Response(response=error, status=404,
                        mimetype="application/json")

    else:
        serializer = AddressJsonSerializer()
        result = serializer.serialize(address)
        return Response(response=result, status=200,
                        mimetype="application/json")

    # TODO: If it's not a perfect match, do we want to do something like a
    # soundex or some other fuzzy match?