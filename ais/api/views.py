"""
Does three primary things:
* Geocoding lat/lng to addresses
* Standardizing addresses
* Providing identifiers for other systems
"""
from collections import OrderedDict
from itertools import chain
from flask import Response, request, redirect, url_for
from flask_cachecontrol import cache_for
from flasgger.utils import swag_from
from geoalchemy2.shape import to_shape
from geoalchemy2.functions import ST_Transform
from sqlalchemy import func, desc
from passyunk.parser import PassyunkParser
from ais import app, util, app_db as db
from ais.models import Address, AddressSummary, StreetIntersection, StreetSegment, Geocode, AddressTag, DorParcel, PwdParcel, OpaProperty, ENGINE_SRID
from ..util import NotNoneDict
from .errors import json_error
from .paginator import QueryPaginator, Paginator
from .serializers import AddressJsonSerializer, IntersectionJsonSerializer, ServiceAreaSerializer, AddressTagSerializer

config = app.config

def json_response(*args, **kwargs):
    return Response(*args, mimetype='application/json', **kwargs)

def validate_page_param(request, paginator):
    page_str = request.args.get('page', '1')

    try:
        page_num = paginator.validate_page_num(page_str)
    except QueryPaginator.ValidationError as e:
        error = json_error(404, e.message, e.data)
        return None, error

    return page_num, None

# def get_tag_data(addresses):
#     all_tags = {}
#     for address, geocode_type, geom in addresses:
#         tag_map = {}
#         tags = AddressTag.query \
#             .filter_tags_by_address(address.street_address)
#         # TODO: If no tags, filter on base/in-range/overlapping number addresses. If still none, return 404.
#         for tag in tags:
#             if not tag.key in tag_map:
#                 tag_map[tag.key] = []
#             tag_map[tag.key].append(tag)
#
#         all_tags[address.street_address] = tag_map
#
#     return all_tags

def get_tag_data(addresses):
    street_addresses = [address.street_address for address, geocode_type, geom in addresses]
    tags = AddressTag.query \
        .filter(AddressTag.street_address.in_(street_addresses))
    # TODO: If no tags, filter on base/in-range/overlapping number addresses. If still none, return 404.
    all_tags = {}
    for tag in tags:
        if not tag.street_address in all_tags:
            all_tags[tag.street_address] = {}
        if not tag.key in all_tags[tag.street_address]:
            all_tags[tag.street_address][tag.key] = []
        all_tags[tag.street_address][tag.key].append(tag)
    return all_tags


@app.errorhandler(404)
@app.errorhandler(500)
def handle_errors(e):
    code = getattr(e, 'code', 500)
    description = getattr(e, 'description', None)
    error = json_error(code, description, None)
    return json_response(response=error, status=code)

def unmatched_response(**kwargs):
    #print("unmatched_response")
    query = kwargs.get('query')
    parsed = kwargs.get('parsed')
    search_type = kwargs.get('search_type')
    normalized_address = kwargs.get('normalized_address')
    address = kwargs.get('address')

    if not address:
        # Fake 'type' as 'address' in order to create Address object for AddressJsonSerializer response
        parsed['type'] = 'address'
        address = Address(parsed)
        #print(address)
        address.street_address = parsed['components']['output_address']
        address.street_code = parsed['components']['street']['street_code']
        address.seg_id = parsed['components']['cl_seg_id']
        address.usps_bldgfirm = parsed['components']['mailing']['bldgfirm']
        address.usps_type = parsed['components']['mailing']['uspstype']
        address.election_block_id = parsed['components']['election']['blockid']
        address.election_precinct = parsed['components']['election']['precinct']
        address.li_address_key = None
        address.pwd_account_nums = None

    addresses = (address,)
    paginator = Paginator(addresses)
    # addresses_count = paginator.collection_size

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        # return json_response(response=error, status=error['status'])
        return json_response(response=error, status=404)

    srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']
    # crs = {'type': 'name', 'properties': {'name': 'EPSG:{}'.format(srid)}}
    crs = {'type': 'link', 'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

    # Render the response
    addresses_page = paginator.get_page(page_num)

    # Use AddressJsonSerializer
    serializer = AddressJsonSerializer(
        metadata={'search_type': search_type, 'query': query, 'normalized': normalized_address,
                  'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        estimated='parsed'
    )
    result = serializer.serialize_many(addresses_page)

    return json_response(response=result, status=200)


@app.route('/unknown/<path:query>')
@cache_for(hours=1)
def unknown_cascade_view(**kwargs):

    query = kwargs.get('query')
    normalized_address = kwargs.get('normalized_address')
    search_type = kwargs.get('search_type')
    parsed = kwargs.get('parsed')
    seg_id = parsed['components']['cl_seg_id']
    base_address = parsed['components']['base_address']
    sa_data = OrderedDict()
    config = app.config
    centerline_offset = config['GEOCODE']['centerline_offset']
    centerline_end_buffer = config['GEOCODE']['centerline_end_buffer']

    # Make empty address object
    address = Address(parsed)

    address.street_address = parsed['components']['output_address']
    address.street_code = parsed['components']['street']['street_code']
    address.seg_id = parsed['components']['cl_seg_id']
    address.usps_bldgfirm = parsed['components']['mailing']['bldgfirm']
    address.usps_type = parsed['components']['mailing']['uspstype']
    address.election_block_id = parsed['components']['election']['blockid']
    address.election_precinct = parsed['components']['election']['precinct']
    address.li_address_key = None
    address.pwd_account_nums = None

    if not seg_id:
        error = json_error(404, 'Could not find any addresses matching query.',
                           {'query': query, 'normalized': normalized_address, 'search_type': search_type})
        return json_response(response=error, status=404)
        # return unmatched_response(query=query, parsed=parsed, normalized_address=normalized_address,
        #                           search_type=search_type, address=address)

    # CASCADE TO STREET SEGMENT
    cascadedseg = StreetSegment.query \
        .filter_by_seg_id(seg_id) #if seg_id else None

    cascadedseg = cascadedseg.first()

    if not cascadedseg:
        error = json_error(404, 'Could not find any addresses matching query.',
                           {'query': query, 'normalized': normalized_address, 'search_type': search_type})
        return json_response(response=error, status=404)
        # return unmatched_response(query=query, parsed=parsed, normalized_address=normalized_address,
        #                           search_type=search_type, address=address)

    # Get address side of street centerline segment
    seg_side = "R" if cascadedseg.right_from % 2 == address.address_low % 2 else "L"
    # Check if address low num is within centerline seg full address range with parity:
    from_num, to_num = (cascadedseg.right_from, cascadedseg.right_to) if seg_side == "R" else (cascadedseg.left_from, cascadedseg.left_to)
    # if not from_num <= address.address_low <= to_num:
    #     error = json_error(404, 'Address number is out of range.',
    #                        {'query': query, 'normalized': normalized_address, 'search_type': search_type})
    #     return json_response(response=error, status=404)

    # Get geom from true_range view item with same seg_id
    true_range_stmt = '''
                    Select true_left_from, true_left_to, true_right_from, true_right_to
                     from true_range
                     where seg_id = {seg_id}
                '''.format(seg_id=cascadedseg.seg_id)
    true_range_result = db.engine.execute(true_range_stmt).fetchall()
    true_range_result = list(chain(*true_range_result))
    # Get side delta (address number range on seg side - from true_range if exists else from centerline seg)
    if true_range_result and seg_side=="R" and true_range_result[3] is not None and true_range_result[2] is not None:
        side_delta = true_range_result[3] - true_range_result[2]
        cascade_geocode_type = 'true_range'
    elif true_range_result and seg_side=="L" and true_range_result[1] is not None and true_range_result[0] is not None:
        side_delta = true_range_result[1] - true_range_result[0]
        cascade_geocode_type = 'true_range'
    else:
        # side_delta = cascadedseg.right_to - cascadedseg.right_from if seg_side == "R" \
        #     else cascadedseg.left_to - cascadedseg.left_from
        side_delta = to_num - from_num
        cascade_geocode_type = 'full_range'
    if side_delta == 0:
        distance_ratio = 0.5
    else:
        distance_ratio = (address.address_low - cascadedseg.right_from) / side_delta

    shape = to_shape(cascadedseg.geom)

    # New method: interpolate buffered
    seg_xsect_xy=util.interpolate_buffered(shape, distance_ratio, centerline_end_buffer)
    seg_xy = util.offset(shape, seg_xsect_xy, centerline_offset, seg_side)

    # GET INTERSECTING SERVICE AREAS
    sa_stmt = '''
                with foo as (
                    SELECT layer_id, value
                    from service_area_polygon
                    where ST_Intersects(geom, ST_GeometryFromText('SRID={srid};{shape}'))
                    )
                SELECT DISTINCT ON (cols.layer_id) cols.layer_id, foo.value
                from service_area_layer cols
                left join foo on foo.layer_id = cols.layer_id
        '''.format(shape=seg_xy, srid=ENGINE_SRID)

    result = db.engine.execute(sa_stmt)
    for item in result.fetchall():
        sa_data[item[0]] = item[1]

    addresses = (address,)
    paginator = Paginator(addresses)
    #addresses_count = paginator.collection_size

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        # return json_response(response=error, status=error['status'])
        return json_response(response=error, status=404)

    srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']
    # crs = {'type': 'name', 'properties': {'name': 'EPSG:{}'.format(srid)}}
    crs = {'type': 'link', 'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

    # Render the response
    addresses_page = paginator.get_page(page_num)

    # Use AddressJsonSerializer
    serializer = AddressJsonSerializer(
        metadata={'search_type': search_type, 'query': query, 'normalized': normalized_address, 'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        srid=srid,
        normalized_address=normalized_address,
        base_address=base_address,
        estimated=cascade_geocode_type,
        shape=seg_xy,
        sa_data=sa_data
    )
    result = serializer.serialize_many(addresses_page)
    # result = serializer.serialize_many(addresses_page) if addresses_count > 1 else serializer.serialize(next(addresses_page))

    return json_response(response=result, status=200)


@app.route('/addresses/<path:query>')
@cache_for(hours=1)
@swag_from('docs/addresses.yml')
def addresses(query):
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

    # Batch queries have been depreciated for this endpoint;
    # handle first query of batch query attempts:
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
    # TODO: Passyunk should handle '5249 GERMANTOWN AVE REAR UNIT REAR'
    search_type=normalized_address= ''
    try:
        parsed = PassyunkParser().parse(query)
        search_type = parsed['type']
        normalized_address = parsed['components']['output_address']
    except:
        error = json_error(404, 'Could not parse query.',
                           {'query': query, 'normalized': normalized_address,'search_type': search_type})
        return json_response(response=error, status=404)

    normalized_address = parsed['components']['output_address']
    base_address = parsed['components']['base_address']
    full_num = parsed['components']['address']['full']
    low_num =  parsed['components']['address']['low_num']
    high_num_full = parsed['components']['address']['high_num_full']
    high_num = parsed['components']['address']['high_num']
    street_full = parsed['components']['street']['full']
    unit_type = parsed['components']['address_unit']['unit_type']
    unit_num = parsed['components']['address_unit']['unit_num']
    addr_num = str(low_num) + '-' + str(high_num) if high_num else low_num
    base_address_no_num_suffix = '{} {}'.format(addr_num, street_full)
    search_type = parsed['type']
    loose_filters = OrderedDict([
                                # ('seg_id',int(parsed['components']['cl_seg_id'])),
                                 ('street_name',parsed['components']['street']['name']),
                                 ('address_low',low_num if low_num is not None else full_num),
                                 ('address_low_suffix',parsed['components']['address']['addr_suffix']),
                                 ('address_low_frac',parsed['components']['address']['fractional']),
                                 ('street_predir',parsed['components']['street']['predir']),
                                 ('street_postdir',parsed['components']['street']['postdir']),
                                 ('street_suffix',parsed['components']['street']['suffix']),
    ])

    strict_filters = dict(
        address_high=high_num_full,
        unit_num=unit_num or '',
    )
    # Remove keys with null values:
    filters = loose_filters.copy()
    for key, value in loose_filters.items():
        if value is None:
            del filters[key]

    if unit_num == '':
        strict_filters.update(dict(unit_type=unit_type or '', ))

    filters.update(strict_filters)

    if search_type not in ('address', 'street') or low_num is None:
        error = json_error(404, 'Not a valid address.',
                           {'query': query, 'normalized': normalized_address,'search_type': search_type})
        return json_response(response=error, status=404)

    range = None

    def query_addresses(filters):

        addresses = AddressSummary.query \
                .filter_by(**filters) \
                .filter_by_unit_type(unit_type) #\
        return addresses

    def process_query(addresses, match_type):

        addresses = addresses.include_child_units(
            'include_units' in request.args and request.args['include_units'].lower() != 'false',
            is_range=False if range else high_num_full is not None,
            is_unit=unit_type is not None,
            request=request) \
            .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
            .get_address_geoms(request) \
            .order_by_address()

        # Get tag data
        try:
            all_tags = get_tag_data(addresses)
        except:
            error = json_error(404, 'Invalid query.',
                               {'query': query, 'normalized': normalized_address, 'search_type': search_type,
                                'search_params': requestargs, })
            return json_response(response=error, status=404)

        # Get pagination
        paginator = QueryPaginator(addresses)

        # Ensure that we have results
        addresses_count = paginator.collection_size

        # Handle unmatched addresses TODO: After deciding todo above, update this section (i.e. delete)
        if addresses_count == 0:

            if 'opa_only' in request.args and request.args['opa_only'].lower() != 'false':
                error = json_error(404, 'Could not find any opa addresses matching the query.',
                                   {'query': query, 'normalized': normalized_address, 'search_type': search_type})
                return json_response(response=error, status=404)
            elif 'estimate' in request.args and request.args['estimate'].lower() == 'false':
                error = json_error(404, 'Could not find any known addresses matching the query.',
                                   {'query': query, 'normalized': normalized_address, 'search_type': search_type})
                return json_response(response=error, status=404)
            else:  # Try to cascade to street centerline segment
                return unknown_cascade_view(query=query, normalized_address=normalized_address, search_type=search_type,
                                            parsed=parsed)

        # Validate the pagination
        page_num, error = validate_page_param(request, paginator)
        if error:
            return json_response(response=error, status=404)

        srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']

        crs = {'type': 'link',
               'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

        # Serialize the response
        addresses_page = paginator.get_page(page_num)
        serializer = AddressJsonSerializer(
            metadata={'query': query, 'normalized': normalized_address, 'search_type': search_type,
                      'search_params': requestargs, 'crs': crs},
            pagination=paginator.get_page_info(page_num),
            srid=srid,
            normalized_address=normalized_address,
            base_address=base_address,
            tag_data=all_tags,
            match_type=match_type,
            ref_addr=normalized_address,
        )
        try:
            result = serializer.serialize_many(addresses_page)
            return json_response(response=result, status=200)
        except:
            error = json_error(404, 'Invalid query.',
                               {'query': query, 'normalized': normalized_address, 'search_type': search_type,
                                'search_params': requestargs})
            return json_response(response=error, status=404)


    addresses = query_addresses(filters=filters)
    if addresses.all():
        match_type = 'exact'
        return process_query(addresses, match_type)
    # if no matches, try base_address
    if normalized_address != base_address:
        if 'unit_num' in filters:
            filters_copy = filters.copy()
            filters_copy['unit_num'] = ''
            unit_type = None  # more elegant approach involving filter_by_unit_type preferred
        addresses = query_addresses(filters=filters_copy)
        if addresses.all():
            match_type = 'has_base'
            return process_query(addresses, match_type)
    if base_address != base_address_no_num_suffix:
        filters_copy = filters.copy()
        if 'unit_num' in filters:
            filters_copy['unit_num'] = ''
            unit_type = None
        if 'address_low_suffix' in filters_copy:
            del filters_copy['address_low_suffix']
        if 'address_low_frac' in filters_copy:
            del filters_copy['address_low_frac']
        addresses = query_addresses(filters=filters_copy)
        if addresses.all():
            match_type = 'has_base_no_suffix'
            return process_query(addresses, match_type)
    # # If no matches and is ranged address, try non-ranged low_num address
    if high_num:
        # TODO: handle overlapping addresses
        filters_copy = filters.copy()
        del filters_copy['address_high']
        range = True
        addresses = query_addresses(filters=filters_copy)
        if addresses.all():
            match_type = 'in_range'
            return process_query(addresses, match_type)
        if normalized_address != base_address:
            if 'unit_num' in filters:
                filters_copy['unit_num'] = ''
                unit_type = None  # more elegant approach involving filter_by_unit_type preferred
            addresses = query_addresses(filters=filters_copy)
            if addresses.all():
                match_type = 'in_range_has_base'
                return process_query(addresses, match_type)
        if base_address != base_address_no_num_suffix:
            if 'address_low_suffix' in filters_copy:
                del filters_copy['address_low_suffix']
            if 'address_low_frac' in filters_copy:
                del filters_copy['address_low_frac']
            addresses = query_addresses(filters=filters_copy)
            if addresses.all():
                match_type = 'in_range_has_base_no_suffix'
                return process_query(addresses, match_type)


    if not addresses.all(): # TODO: Decide what to do here!
        if 'opa_only' in request.args and request.args['opa_only'].lower() != 'false':
            error = json_error(404, 'Could not find any opa addresses matching the query.',
                                    {'query': query, 'normalized': normalized_address, 'search_type': search_type})
            return json_response(response=error, status=404)
        elif 'estimate' in request.args and request.args['estimate'].lower() == 'false':
            error = json_error(404, 'Could not find any known addresses matching the query.',
                                    {'query': query, 'normalized': normalized_address, 'search_type': search_type})
            return json_response(response=error, status=404)
        else: # Try to cascade to street centerline segment
            return unknown_cascade_view(query=query, normalized_address=normalized_address, search_type=search_type, parsed=parsed)


@app.route('/block/<path:query>')
@cache_for(hours=1)
@swag_from('docs/block.yml')
def block(query):
    """
    Looks up information about the 100-range that the given address falls
    within.

    TODO: Consider matching the segment ID and finding the low and high. This
          would be instead of hard-coding a low of 0 and high of 100. Maybe this
          would go at a new route, like `segment` or `block-face`.
    """
    query = query.strip('/')
    parsed = PassyunkParser().parse(query)

    # search_type = parsed['type']
    # if search_type != 'block':
    #     error = json_error(404, 'Not a valid block query.',
    #                        {'query': query, 'search_type': search_type})
    #     return json_response(response=error, status=404)
    # Handle address direct queries to this endpoint as block queries
    search_type = 'block'
    normalized_address = parsed['components']['output_address']

    # Ensure that we can get a valid address number
    try:
        address_num = int(parsed['components']['address']['low_num']
                          if parsed['components']['address']['low_num'] is not None
                          else parsed['components']['address']['full'])
    except (TypeError, ValueError):
        error = json_error(404, 'No valid block number provided.',
                           {'query': query, 'normalized': normalized_address, 'search_type': search_type})
        return json_response(response=error, status=404)

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
        .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
        .get_address_geoms(request)

    addresses = addresses.order_by_address()
    paginator = QueryPaginator(addresses)

    # Ensure that we have results
    addresses_count = paginator.collection_size
    #print(addresses_count)
    if addresses_count == 0:
        if 'opa_only' in request.args and request.args['opa_only'].lower() != 'false':
            error = json_error(404, 'Could not find any opa addresses matching query.',
                                    {'query': query, 'normalized': normalized_address,'search_type': search_type})
            return json_response(response=error, status=404)
        else:
            error = json_error(404, 'Could not find any address on a block matching query.',
                               {'query': query, 'normalized': normalized_address, 'search_type': search_type})
            return json_response(response=error, status=404)
        #     return unmatched_response(query=query, parsed=parsed, normalized_address=normalized_address,
        #                               search_type=search_type)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    # Get tag data
    all_tags = get_tag_data(addresses)

    # Serialize the response
    block_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'search_type': search_type, 'query': query, 'normalized': normalized_address, 'search_params': request.args},
        pagination=paginator.get_page_info(page_num),
        srid=request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID'], tag_data=all_tags,
        normalized_address=normalized_address,
    )
    result = serializer.serialize_many(block_page)
    #result = serializer.serialize_many(block_page) if addresses_count > 1 else serializer.serialize(next(block_page))
    return json_response(response=result, status=200)


@app.route('/owner/<query>')
@cache_for(hours=1)
@swag_from('docs/owner.yml')
def owner(query):
    query = query.strip('/')

    owner_parts = query.upper().split()

    # Match a set of addresses
    addresses = AddressSummary.query\
        .filter_by_owner(*owner_parts)\
        .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
        .get_address_geoms(request) \
        .order_by_address()

    # Get pagination
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
        return json_response(response=error, status=404)

    srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']

    crs = {'type': 'link', 'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

    # Get tag data
    all_tags = get_tag_data(addresses)

    # Serialize the response
    page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'search_type': 'owner', 'query': query, 'normalized': owner_parts, 'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        srid=srid, tag_data=all_tags,
    )
    result = serializer.serialize_many(page)

    return json_response(response=result, status=200)


@app.route('/account/<query>')
@cache_for(hours=1)
@swag_from('docs/account.yml')
def account(query):
    """
    Looks up information about the property with the given OPA account number.
    Returns all addresses with opa_account_num matching query.
    """
    query = query.strip('/')
    parsed = PassyunkParser().parse(query)
    search_type = parsed['type']
    normalized = parsed['components']['output_address']

    # addresses = AddressSummary.query\
    #     .filter(AddressSummary.opa_account_num==query)\
    #     .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
    #     .get_address_geoms(request) \
    #     .sort_by_source_address_from_search_type(search_type)

    tagged_opa_account_nums = OpaProperty.query \
        .filter(OpaProperty.account_num == normalized).all()
    street_addresses = tuple(set([x.street_address for x in tagged_opa_account_nums]))

    addresses = AddressSummary.query \
        .filter(AddressSummary.street_address.in_(street_addresses)) \
        .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
        .get_address_geoms(request) \
        .order_by(desc(AddressSummary.street_address.in_(street_addresses)))

    # Get pagination
    paginator = QueryPaginator(addresses)

    # Ensure that we have results
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find any addresses matching query.',
                           {'query': query,'search_type': search_type})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']

    crs = {'type': 'link', 'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

    # Get tag data
    all_tags = get_tag_data(addresses)

    # Serialize the response
    addresses_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'search_type': search_type, 'query': query, 'normalized': normalized, 'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        srid=srid, tag_data=all_tags,
    )
    result = serializer.serialize_many(addresses_page)

    return json_response(response=result, status=200)


@app.route('/pwd_parcel/<query>')
@cache_for(hours=1)
@swag_from('docs/pwd_parcel.yml')
def pwd_parcel(query):
    """
    Looks up information about the property with the given PWD parcel id.
    """
    if not (query.isdigit() and len(query) < 8):
        error = json_error(404, 'Not a valid pwd_parcel_id.',
                           {'query': query})
        return json_response(response=error, status=404)
    search_type = 'pwd_parcel_id'
    # addresses = AddressSummary.query\
    #     .filter(AddressSummary.pwd_parcel_id==query) \
    #     .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
    #     .get_address_geoms(request) \
    #     .sort_by_source_address_from_search_type(search_type)

    tagged_pwd_parcel_ids = PwdParcel.query \
        .filter(PwdParcel.parcel_id==query).all()
    street_addresses = tuple(set([x.street_address for x in tagged_pwd_parcel_ids]))

    addresses = AddressSummary.query \
        .filter(AddressSummary.street_address.in_(street_addresses)) \
        .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
        .get_address_geoms(request)\
        .order_by(desc(AddressSummary.street_address.in_(street_addresses)))

    # Get pagination
    paginator = QueryPaginator(addresses)

    addresses_count = paginator.collection_size

    if addresses_count == 0:
        error = json_error(404, 'Could not find any addresses matching query.',
                           {'query': query, 'search_type': search_type})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']

    crs = {'type': 'link', 'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

    # Get tag data
    all_tags = get_tag_data(addresses)

    # Serialize the response
    addresses_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'search_type': search_type, 'query': query, 'normalized': query, 'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        srid=srid, tag_data=all_tags,
    )
    result = serializer.serialize_many(addresses_page)

    return json_response(response=result, status=200)


@app.route('/dor_parcel/<query>')
@cache_for(hours=1)
@swag_from('docs/mapreg.yml')
def dor_parcel(query):
    """
    Looks up information about the property with the given DOR parcel id.
    """
    parsed = PassyunkParser().parse(query)
    normalized_id = parsed['components']['output_address']
    search_type = parsed['type']
    if search_type != 'mapreg':
        error = json_error(404, 'Not a valid dor_parcel_id.',
                           {'query': query})
        return json_response(response=error, status=404)

    tagged_dor_parcel_ids = DorParcel.query  \
        .filter(DorParcel.parcel_id==normalized_id).all()
    street_addresses = tuple(set([x.street_address for x in tagged_dor_parcel_ids]))

    addresses = AddressSummary.query \
        .filter(AddressSummary.street_address.in_(street_addresses)) \
        .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false') \
        .get_address_geoms(request)\
        .order_by(desc(AddressSummary.street_address.in_(street_addresses)))

    # Get pagination
    paginator = QueryPaginator(addresses)

    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find any addresses matching query.',
                           {'query': query, 'search_type': search_type})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']

    crs = {'type': 'link', 'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

    #Get tag data
    all_tags = get_tag_data(addresses)

    # Serialize the response
    addresses_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'search_type': search_type, 'query': query, 'normalized': normalized_id, 'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        srid=srid, tag_data=all_tags,
    )
    result = serializer.serialize_many(addresses_page)

    return json_response(response=result, status=200)


@app.route('/intersection/<path:query>')
@cache_for(hours=1)
@swag_from('docs/intersection.yml')
def intersection(query):
    '''
    Called by search endpoint if search_type == "intersection_addr"
    '''
    query = query.strip('/')
    parsed = PassyunkParser().parse(query)
    search_type = 'intersection' if parsed['type'] == 'intersection_addr' else parsed['type']

    if search_type != 'intersection':
        error = json_error(404, 'Not a valid intersection query.',
                           {'query': query})
        return json_response(response=error, status=404)

    street_1_full = parsed['components']['street']['full']
    street_1_name = parsed['components']['street']['name']
    street_1_predir = parsed['components']['street']['predir']
    street_1_postdir = parsed['components']['street']['postdir']
    street_1_suffix = parsed['components']['street']['suffix']
    street_1_code = parsed['components']['street']['street_code']
    street_2_full = parsed['components']['street_2']['full']
    street_2_name = parsed['components']['street_2']['name']
    street_2_predir = parsed['components']['street_2']['predir']
    street_2_postdir = parsed['components']['street_2']['postdir']
    street_2_suffix = parsed['components']['street_2']['suffix']
    street_2_code = parsed['components']['street_2']['street_code']
    street_code_min = str(min(int(street_1_code), int(street_2_code))) if street_1_code and street_2_code else None
    street_code_max = str(max(int(street_1_code), int(street_2_code))) if street_1_code and street_2_code else None

    if street_code_min and street_code_max:
        strict_filters = dict(
            street_1_code=street_code_min,
            street_2_code=street_code_max,
        )
        filters = strict_filters.copy()
        intersections = StreetIntersection.query \
            .filter_by(**filters) \
            .order_by_intersection()
    else:
        loose_filters = NotNoneDict(
            street_1_code=street_code_min,
            street_2_code=street_code_max,
            street_1_predir=street_1_predir,
            street_1_postdir=street_1_postdir,
            street_1_suffix=street_1_suffix,
            street_2_predir=street_2_predir,
            street_2_postdir=street_2_postdir,
            street_2_suffix=street_2_suffix,
        )
        strict_filters = dict(
            street_1_name=street_1_name,
            street_2_name=street_2_name,
        )
        filters = strict_filters.copy()
        filters.update(loose_filters)
        intersections = StreetIntersection.query \
            .filter_by(**filters)

    # if no intersections matched, try reversing street_1 and street_2 attributes
    if not intersections.first():
        loose_filters = NotNoneDict(
            street_2_code=street_code_min,
            street_1_code=street_code_max,
            street_1_predir=street_2_predir,
            street_1_postdir=street_2_postdir,
            street_1_suffix=street_2_suffix,
            street_2_predir=street_1_predir,
            street_2_postdir=street_1_postdir,
            street_2_suffix=street_1_suffix,
        )
        strict_filters = dict(
            street_1_name=street_2_name,
            street_2_name=street_1_name,
        )
        filters = strict_filters.copy()
        filters.update(loose_filters)
        intersections = StreetIntersection.query \
            .filter_by(**filters)

    intersections = intersections.order_by_intersection()
    intersections = intersections.distinct(StreetIntersection.street_1_full, StreetIntersection.street_2_full)

    # Get pagination
    paginator = QueryPaginator(intersections)

    intersections_count = paginator.collection_size

    if intersections_count == 0:
        error = json_error(404, 'Could not find intersection matching query.',
                           {'query': query, 'search_type': search_type, 'normalized': {'street_name_1': street_1_name, 'street_name_2': street_2_name}})
        return json_response(response=error, status=404)
    else:
        match_type = 'exact'

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    srid = request.args.get('srid') if 'srid' in request.args else config['DEFAULT_API_SRID']

    crs = {'type': 'link', 'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}

    # Serialize the response:
    intersections_page = paginator.get_page(page_num)
    normalized = intersections.first().street_1_full + ' & ' + intersections.first().street_2_full if intersections_count == 1 else street_1_full + ' & ' + street_2_full
    serializer = IntersectionJsonSerializer(
        metadata={'search_type': search_type, 'query': query, 'normalized': normalized, 'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        srid=srid,
        match_type=match_type)

    result = serializer.serialize_many(intersections_page)

    return json_response(response=result, status=200)


@app.route('/reverse_geocode/<path:query>')
@cache_for(hours=1)
@swag_from('docs/reverse_geocode.yml')
def reverse_geocode(query):

    query = query.strip('/')
    parsed = PassyunkParser().parse(query)
    search_type_out = 'coordinates'
    search_type = parsed['type']
    normalized = parsed['components']['output_address']
    srid_map = {'stateplane': 2272, 'latlon': 4326}
    try:
        srid = str(srid_map[search_type])
    except:
        error = json_error(404, 'Please format your query in State Plane or latitude longitude coordinates separated by a space or comma.',
                           {'search_type': search_type, 'query': query, 'normalized': normalized})
        return json_response(response=error, status=404)
    engine_srid = str(ENGINE_SRID)  # check if necessary
    crs = {'type': 'link',
           'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}
    x, y = normalized.split(",", 1)
    search_radius = request.args.get('search_radius') if 'search_radius' in request.args else config['DEFAULT_SEARCH_RADIUS']
    search_radius = min(int(search_radius), config['MAXIMUM_SEARCH_RADIUS'])
    # queries the geocode table by coordinates for the record with the nearest coordinates having \
    # geocode type = pwd_curb, dor_curb, true_range or centerline
    reverse_geocode_stmt = '''
        SELECT street_address, geocode_type
        from geocode
        where ST_DWITHIN(geom, ST_Transform(ST_GeometryFromText('POINT({x} {y})',{srid}),{engine_srid}), {search_radius})
          AND geocode_type IN ({pwd_curb}, {dor_curb}, {true_range})
        ORDER BY
            geom <-> ST_Transform(ST_GeometryFromText('POINT({x} {y})',{srid}),{engine_srid}),
            length(street_address) asc
        LIMIT 1
        '''.format(x=x, y=y, srid=srid, engine_srid=engine_srid, pwd_curb=7, dor_curb=8, true_range=5, centerline=6,
                   search_radius=search_radius)

    results = db.engine.execute(reverse_geocode_stmt)
    result = None
    for result in results:
        street_address, geocode_type = result
        break

    if not result:
        error = json_error(404, 'Could not find any addresses matching query.',
                           {'query': query, 'normalized': normalized, 'search_type': search_type})
        return json_response(response=error, status=404)

    parsed = PassyunkParser().parse(street_address)
    normalized_address = parsed['components']['output_address']
    unit_type = parsed['components']['address_unit']['unit_type']
    unit_num = parsed['components']['address_unit']['unit_num']
    high_num = parsed['components']['address']['high_num_full']
    low_num = parsed['components']['address']['low_num']
    base_address = parsed['components']['base_address']

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
        unit_num=unit_num or '',
    )
    # if unit num is null, add unit_type to strict filter
    if unit_num == '':
        strict_filters.update(dict(unit_type=unit_type or '', ))

    filters = strict_filters.copy()
    filters.update(loose_filters)
    addresses = AddressSummary.query \
        .filter_by(**filters) \
        .filter_by_unit_type(unit_type) \
        .include_child_units(
        'include_units' in request.args and request.args['include_units'].lower() != 'false',
        is_range=high_num is not None,
        is_unit=unit_type is not None,
        request=request) \
        .outerjoin(Geocode, Geocode.street_address == AddressSummary.street_address)\
        .filter(Geocode.geocode_type == geocode_type) \
        .add_columns(Geocode.geocode_type, ST_Transform(Geocode.geom, srid)) \
        .exclude_non_opa('opa_only' in request.args and request.args['opa_only'].lower() != 'false')

    addresses = addresses.order_by_address()

    # Get pagination
    paginator = QueryPaginator(addresses)
    # Ensure that we have results
    addresses_count = paginator.collection_size
    # Handle unmatched addresses
    if addresses_count == 0:
        error = json_error(404, 'Could not find any addresses matching query.',
                           {'search_type': search_type, 'query': query, 'normalized': normalized})
        return json_response(response=error, status=404)

    #Get tag data
    all_tags=get_tag_data(addresses)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=404)

    match_type = 'nearest'
    # Serialize the response
    addresses_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'search_type': search_type_out, 'query': query, 'normalized': normalized,
                  'search_params': request.args, 'crs': crs},
        pagination=paginator.get_page_info(page_num),
        srid=srid,
        normalized_address=normalized_address,
        base_address=base_address,
        match_type=match_type, tag_data=all_tags,
    )
    result = serializer.serialize_many(addresses_page)

    return json_response(response=result, status=200)


@app.route('/service_areas/<path:query>')
@cache_for(hours=1)
@swag_from('docs/service_areas.yml')
def service_areas(query):

    query = query.strip('/')
    parsed = PassyunkParser().parse(query)
    search_type = parsed['type']

    if search_type == 'none':
        error = json_error(404, 'There are no intersecting service areas.',
                           {'query': query})
        return json_response(response=error, status=404)

    normalized = parsed['components']['output_address']
    srid_map = {'stateplane': 2272, 'latlon': 4326}
    try:
        srid = str(srid_map[search_type])
    except:
        error = json_error(404, 'Not a valid service_area query.',
                           {'query': query, 'search_type': search_type})
        return json_response(response=error, status=404)
    engine_srid = str(ENGINE_SRID)
    crs = {'type': 'link',
           'properties': {'type': 'proj4', 'href': 'http://spatialreference.org/ref/epsg/{}/proj4/'.format(srid)}}
    x, y = normalized.split(",", 1)
    coords = [float(x), float(y)]
    sa_data = OrderedDict()
    search_type_out = 'coordinates'

    sa_stmt = '''
                with foo as
                (
                SELECT layer_id, value
                from service_area_polygon
                where ST_Intersects(geom, ST_Transform(ST_GeometryFromText('POINT({x} {y})',{srid}),{engine_srid}))
                )
                SELECT DISTINCT ON (cols.layer_id) cols.layer_id, foo.value
                from service_area_layer cols
                left join foo on foo.layer_id = cols.layer_id
            '''.format(srid=srid, engine_srid=engine_srid,x=x, y=y)

    result = db.engine.execute(sa_stmt)
    for item in result.fetchall():
        sa_data[item[0]] = item[1]

    if all(value == None for value in sa_data.values()):
        error = json_error(404, 'There are no intersecting service areas.',
                           {'search_type': search_type, 'query': query, 'normalized': normalized})
        return json_response(response=error, status=404)

    # Use ServiceAreaSerializer
    serializer = ServiceAreaSerializer(
        metadata={'search_type': search_type_out, 'query': query,
                  'search_params': request.args, 'normalized': normalized, 'crs': crs},
        sa_data=sa_data, coordinates=coords,
    )
    result = serializer.serialize()

    return json_response(response=result, status=200)


#@app.route('/street/<path:query>')
#@cache_for(hours=1)
def street(query):
    error = json_error(404, 'Could not find any addresses matching query.',
                       {'query': query})
    return json_response(response=error, status=404)

# from flask_sqlalchemy import get_debug_queries
# @app.after_request
# def after_request(response):
#     for query in get_debug_queries():
#         app.logger.warning("SLOW QUERY: %s\nParameters: %s\nDuration: %fs\nContext: %s\n" % (query.statement, query.parameters, query.duration, query.context))
#     return response

@app.route('/search/<path:query>')
@cache_for(hours=1)
@swag_from('docs/search.yml')
def search(query):
    """
    API Endpoint for various types of geocoding (not solely addresses)
    """
    #query_original = query
    query = query.strip('/')

    # Limit queries to < 80 characters total:
    arg_len = 0
    entry_length = len(query)
    if request.args:
        for arg in request.args:
            arg_len += len(arg)
        entry_length = entry_length + arg_len
    if not entry_length < 80:
        error = json_error(404, 'Query exceeds character limit.',
                           {'query': query})
        return json_response(response=error, status=404)

    #TODO: Check for illegal characters in query

    # We are not supporting batch queries, so if attempted only take first query
    query = query[:query.index(';')] if ';' in query else query

    parser_search_type_map = {
        'address': addresses,
        'intersection_addr': intersection,
        'opa_account': account,
        'mapreg': dor_parcel,
        'block': block,
        'latlon': reverse_geocode,
        'stateplane': reverse_geocode,
        'street': addresses,
    }
    try:
        parsed = PassyunkParser().parse(query)
    except:
        error = json_error(404, 'Could not parse query.',
                           {'query': query})
        return json_response(response=error, status=404)
    search_type = parsed['type']
    normalized_address = parsed['components']['output_address']
    # TODO: Pass search_type (or parsed) to view function to avoid reparsing
    if search_type != 'none':
        # get the corresponding view function
        try:
            view = parser_search_type_map[search_type]
            # call it
            return view(query)
        except:
            error = json_error(404, 'Invalid query.',
                               {'query': query, 'normalized': normalized_address,'search_type': search_type})
            return json_response(response=error, status=404)

    # Handle search type = 'none:
    else:
        # Handle queries of pwd_parcel ids:
        if query.isdigit() and len(query) < 8:
            return pwd_parcel(query)
        else:
            error = json_error(404, 'Query not recognized.',
                               {'query': query})
            return json_response(response=error, status=404)


@app.route("/")
def base_landing():
    # url = url_for('apidocs', _external=True) + '/index.html'
    url = url_for('base_landing', _external=True) + 'index.html'
    #print(url)
    #return redirect(url_for(base_landing, _external=True) + '//apidocs/index.html')
    return redirect(url, code=302)
    # return """
    #   <h1> Welcome to AIS API</h1>
    #   <ul>
    #      <li><a href="/addresses/">Addresses</a></li>
    #      <li><a href="/block/">Block</a></li>
    #      <li><a href="/intersection/">Intersection</a></li>
    #      <li><a href="/account/">OPA Account Number</a></li>
    #      <li><a href="/mapreg/">MapReg</a></li>
    #      <li><a href="/pwd_parcel/">PWD Parcel ID</a></li>
    #      <li><a href="/owner/">Owner</a></li>
    #      <li><a href="/search/">Search</a></li>
    #
    #   </ul>
    # """