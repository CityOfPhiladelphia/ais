import json
import pytest
from ais import app, app_db
from operator import eq, gt

@pytest.fixture
def client():
    app.config['TESTING'] = True
    return app.test_client()

def assert_status(response, *expected_status_codes):
    assert response.status_code in expected_status_codes, (
        'Expected status {}; received {}. Full response was {}.').format(
        expected_status_codes, response.status_code, response.get_data())

def assert_num_results(data, expected_num_results, op=eq):
    actual_num_results = data['total_size']
    assert op(actual_num_results, expected_num_results), (
        "Expected {} {} results; received {}. Full response "
        "was {}").format(
        op.__name__, expected_num_results, actual_num_results,
        data)

def assert_attr(feature, property_name, expected_value):
    actual_address = feature['properties'][property_name]
    assert actual_address == expected_value, (
        'Expected {} of {}; received {}.').format(
        property_name, expected_value, actual_address)

def assert_opa_address(feature, expected_address):
    assert_attr(feature, 'opa_address', expected_address)

def test_single_address_has_single_result(client):
    response = client.get('/addresses/1922 SARTAIN ST')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

def test_range_address_has_single_result(client):
    response = client.get('/addresses/523-25 N Broad St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '523-25 N BROAD ST')

def test_child_beginning_range_has_single_result(client):
    response = client.get('/addresses/523 N Broad St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '523-25 N BROAD ST')

def test_child_end_range_has_single_result(client):
    response = client.get('/addresses/525 N Broad St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '523-25 N BROAD ST')

def test_child_inside_range_has_single_result(client):
    response = client.get('/addresses/1307 S 6th St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '1307-11 S 6TH ST')

def test_range_parity_is_respected(client):
    # Revised to expect cascade and estimated address from true range
    response = client.get('/addresses/524 N Broad St')
    data = json.loads(response.get_data().decode())
    feature = data['features'][0]
    match_type = feature['match_type']
    assert_status(response, 200)
    assert(match_type == 'unmatched')

def test_base_address_has_units_with_base_first(client):
    response = client.get('/addresses/600 S 48th St?include_units')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1, op=gt)

    feature = data['features'][0]
    assert_attr(feature, 'street_address', '600 S 48TH ST')

def test_geometry_is_lat_lng_by_default(client):
    response = client.get('/addresses/600 S 48th St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    feature = data['features'][0]
    # Make sure the point is in the Philadelphia region
    coords = tuple(feature['geometry']['coordinates'])
    assert (-76, 39) < coords < (-74, 41),\
        ('Coordinates do not appear to be in Philadelphia, or do not represent '
         'a longitude, latitude: {}').format(coords)

def test_ranged_address_has_units_with_base_first(client):
    response = client.get('/addresses/1801-23 N 10th St?include_units')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1, op=gt)

    feature = data['features'][0]
    assert_attr(feature, 'street_address', '1801-23 N 10TH ST')

def test_child_address_has_units_with_base_first(client):
    response = client.get('/addresses/1801 N 10th St?include_units')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1, op=gt)

    feature = data['features'][0]
    assert_attr(feature, 'street_address', '1801 N 10TH ST')
    assert_opa_address(feature, '1801-23 N 10TH ST')

def test_child_address_has_opa_units(client):
    response = client.get('/addresses/11 N 2nd St?include_units&opa_only')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1, op=gt)

def test_child_address_has_all_units_in_ranged_address(client):
    response = client.get('/addresses/1801 N 10th St')
    assert_status(response, 200)
    child_data = json.loads(response.get_data().decode())

    response = client.get('/addresses/1801-23 N 10th St')
    assert_status(response, 200)
    ranged_data = json.loads(response.get_data().decode())

    assert child_data['total_size'] == ranged_data['total_size'], \
        ('Child address has {} results, whereas the ranged address has {} '
         'results.').format(child_data['total_size'], ranged_data['total_size'])

@pytest.mark.skip(reason="todo - return OPA source address instead of parsed OPA street_address")
def test_unit_address_in_db(client):
    response = client.get('/addresses/826-28 N 3rd St # 1')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '826-28 N 3RD ST # 1')

@pytest.mark.skip(reason="todo - return OPA full address")
def test_unit_address_without_unit_num_in_db(client):
    UNIT_SQL = '''
        SELECT unit.street_address
          FROM address_summary AS unit
          JOIN address_link ON address_1 = unit.street_address
          JOIN address_summary AS base ON address_2 = base.street_address

        WHERE relationship = 'has base'
          AND unit.opa_account_num IS NOT NULL
          AND unit.opa_account_num != ''
          AND unit.opa_account_num != base.opa_account_num
          AND unit.unit_num IN ('', NULL)

        LIMIT 1
    '''
    result = app_db.engine.execute(UNIT_SQL)
    street_address = result.first()[0]

    response = client.get('/addresses/{}?opa_only'.format(street_address))
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, street_address)

def test_unit_address_not_in_db(client):
    response = client.get('/addresses/826-28 N 3rd St # 11')
    # assert_status(response, 404)

@pytest.mark.skip(reason="todo - return OPA full address")
def test_synonymous_unit_types_found(client):
    # APT
    response = client.get('/addresses/826-28 N 3rd St Apartment 1')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '826-28 N 3RD ST # 1')

    # UNIT
    response = client.get('/addresses/826-28 N 3rd St Unit 1')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '826-28 N 3RD ST # 1')

    # STE
    response = client.get('/addresses/826-28 N 3rd St Ste 1')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '826-28 N 3RD ST # 1')

def test_nonsynonymous_unit_types_not_used(client):
    # Revised to expect cascade and estimated address from true range
    # TODO:
    response = client.get('/addresses/826-28 N 3rd St Floor 1')
    #assert_status(response, 404)
    data = json.loads(response.get_data().decode())
    feature = data['features'][0]
    match_type = feature['match_type']
    assert_status(response, 200)
    # assert (match_type == 'unmatched')
    assert (match_type == 'has_base')

def test_filter_for_only_opa_addresses(client):
    response = client.get('/addresses/1234 Market St?opa_only&include_units')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

@pytest.mark.skip(reason="batch queries no longer supported")
def test_multiple_addresses_have_all_units(client):
    response = client.get('/addresses/1801 N 10th St?include_units')
    assert_status(response, 200)
    data = json.loads(response.get_data().decode())
    num_results_1 = data['total_size']

    response = client.get('/addresses/600 S 48th St?include_units')
    assert_status(response, 200)
    data = json.loads(response.get_data().decode())
    num_results_2 = data['total_size']

    response = client.get('/addresses/1801 N 10th St;600 S 48th St?include_units')
    assert_status(response, 200)
    data = json.loads(response.get_data().decode())
    assert_num_results(data, num_results_1 + num_results_2)

def test_fractional_addresses_are_ok(client):
    response = client.get('/addresses/13 1/2 Manheim St')
    assert_status(response, 200)
    data = json.loads(response.get_data().decode())
    assert data['query'] == '13 1/2 Manheim St'

def test_allows_0_as_address_low_num(client):
    response = client.get('/addresses/0-98 Sharpnack')
    # data = json.loads(response.get_data().decode())
    # feature = data['features'][0]
    # assert_status(response, 200)
    # assert feature['match_type'] == 'parsed'
    assert_status(response, 404)

def test_allows_0_as_block_low_num(client):
    response = client.get('/block/0 N Front St')
    assert_status(response, 200)

def test_only_returns_non_child_addresses_on_block(client):
    response = client.get('/block/0-98 Front')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    addresses = set(f['properties']['street_address'] for f in data['features'])
    assert '14-18 N FRONT ST' in addresses
    assert '18 N FRONT ST' not in addresses

def test_address_query_can_end_in_comma(client):
    response = client.get('/addresses/1927 N PATTON ST,')
    assert_status(response, 200)

def test_opa_query_returns_child_address(client):
    CHILD_SQL = '''
        SELECT child.street_address, parent.street_address
        FROM address_summary AS child
          JOIN address_link ON address_1 = child.street_address
          JOIN address_summary AS parent ON address_2 = parent.street_address
        WHERE relationship = 'in range'
          AND child.opa_account_num != ''
          AND parent.opa_account_num = child.opa_account_num
          AND child.address_low != parent.address_low
          AND child.address_low != parent.address_high
        LIMIT 1
    '''
    result = app_db.engine.execute(CHILD_SQL)
    child_address, parent_address = result.first()

    response = client.get('/addresses/{}?opa_only'.format(child_address))
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    # TODO: reconcile exception
    if parent_address != '1501-53 N 24TH ST':
        assert_opa_address(feature, parent_address)

def test_block_can_exclude_non_opa(client):
    BLOCK_COUNT_SQL = '''
        SELECT count(*)
        FROM (
          SELECT *
          FROM address_summary
            LEFT OUTER JOIN address_link ON address_link.address_1 = address_summary.street_address
            LEFT OUTER JOIN address_summary AS base_address_summary ON address_link.address_2 = base_address_summary.street_address

          WHERE address_summary.street_predir = 'N'
            AND address_summary.street_name = '10TH'
            AND address_summary.street_suffix = 'ST'
            AND address_summary.address_low >= 1800
            AND address_summary.address_low < 1900

            AND address_summary.opa_account_num != ''
            AND (address_link.relationship = 'has base' OR address_link.relationship = 'overlaps' OR address_link.relationship IS NULL)
            AND (base_address_summary.opa_account_num != address_summary.opa_account_num OR base_address_summary.opa_account_num IS NULL)
          ) AS block_addresses
    '''
    result = app_db.engine.execute(BLOCK_COUNT_SQL)
    block_count = result.first()[0]

    # Ensure that no join collisions happen
    response = client.get('/block/1800 N 10th St?opa_only')
    assert_status(response, 200)

    # Ensure it has the right number of results
    data = json.loads(response.get_data().decode())
    assert_num_results(data, block_count)

def test_invalid_block_raises_404(client):
    response = client.get('/block/abcde')
    assert_status(response, 404)

def test_owner_not_found(client):
    response = client.get('/owner/FLIBBERTIGIBBET')
    assert_status(response, 404)
    #assert_status(response, 200)

def test_general_responses_are_cached(client):
    response = client.get('/addresses/1234 Market St')
    assert response.cache_control.max_age is not None
    assert response.cache_control.max_age > 0

def test_not_found(client):
    response = client.get('/nothinhere/')
    assert_status(response, 404)

    # Ensure that the content is JSON
    response_content = response.get_data().decode()
    try:
        data = json.loads(response_content)
    except ValueError:
        raise Exception('Response is not JSON: {}'.format(response_content))

def test_intersection_query(client):
    # TODO: Make functional without street suffix (st)?
    response = client.get('/search/n 3rd and market st')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    feature = data['features'][0]
    assert feature['ais_feature_type'] == 'intersection'
    response = client.get('/search/broad and girard')
    data = json.loads(response.get_data().decode())
    assert len(data['features']) == 1
    # assert feature['properties']['int_id'] == 21258

def test_intersection_query_no_predir(client):
    # TODO: Make functional without street predir (and st suffix): i.e. 'S 12th and chestnut st' works
    # ^^ Done
    response = client.get('/search/12th and chestnut')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    feature = data['features'][0]
    match_type = feature['match_type']
    # assert match_type == 'parsed'
    assert match_type == 'exact'


def test_cascade_to_true_range(client):
    response = client.get('/search/1050 filbert st')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    feature = data['features'][0]
    assert feature['geometry']['geocode_type'] == 'true_range'
    assert feature['match_type'] == 'unmatched'

def test_cascade_to_full_range(client):
    #response = client.get('/search/3551 ashfield lane')
    response = client.get('/search/3419 ashfield lane')
    data = json.loads(response.get_data().decode())
    feature = data['features'][0]
    assert feature['geometry']['geocode_type'] == 'full_range'
    assert feature['match_type'] == 'unmatched'
    assert_status(response, 200)

def test_query_character_limit(client):
    response = client.get('/search/1234%20market%20st?on_curb&ddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd')
    data = json.loads(response.get_data().decode())
    message = data['message']
    expected = "Query exceeds character limit."
    assert message == expected
    assert_status(response, 404)

def test_match_type_for_address_not_having_address_link(client):
    response = client.get('/search/1849 blair st')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    feature = data['features'][0]
    match_type = feature['match_type']
    assert match_type == 'exact'

def test_unit_type_siblings_match_exact(client):
    response = client.get('/search/337 s camac st apt 3')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    feature = data['features'][0]
    match_type = feature['match_type']
    assert match_type == 'exact'
    response = client.get('/search/337 s camac st unit 3')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    feature = data['features'][0]
    match_type = feature['match_type']
    assert match_type == 'exact'
    response = client.get('/search/1769 frankford ave # 2')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    feature = data['features'][0]
    match_type = feature['match_type']
    assert match_type == 'exact'

def test_addresses_without_pwd_dor_id_return_true_or_full_range_geocode(client):
    response = client.get('/search/2100 KITTY HAWK AVE')
    data = json.loads(response.get_data().decode())
    feature = data['features'][0]
    assert feature['geometry']['geocode_type'] == 'true_range'

def test_address_without_seg_match_returns_404(client):
    response = client.get('/search/2100 SITTY TAWK AVE')
    assert_status(response, 404)


# TESTS for LINKED TAGS CHANGES

def test_addresses_with_unmatching_unit_num_resolves_to_base_address_match(client):
    response = client.get('/search/1769 frankford ave apt 2000')
    data = json.loads(response.get_data().decode())
    features = data['features']
    assert features[0]['match_type'] == 'has_base'

def test_addresses_with_unmatching_unit_num_resolves_to_base_address_match_with_include_units(client):
    response = client.get('/search/1769 frankford ave apt 2000?include_units')
    data = json.loads(response.get_data().decode())
    assert data['total_size'] == 7
    features = data['features']
    assert features[0]['properties']['street_address'] == '1769 FRANKFORD AVE'
    assert features[1]['properties']['street_address'] == '1769 FRANKFORD AVE APT 1'
    assert features[1]['match_type'] == 'has_base_unit_child'

def test_addresses_with_unmatching_high_num_resolves_to_match_with_no_high_num(client):
    response = client.get('/search/1769-75 frankford ave')
    data = json.loads(response.get_data().decode())
    assert data['total_size'] == 1
    features = data['features']
    assert features[0]['match_type'] == 'in_range'

def test_addresses_with_unmatching_high_num_resolves_to_match_with_no_high_num_with_include_units(client):
    response = client.get('/search/1769-75 frankford ave?include_units')
    data = json.loads(response.get_data().decode())
    assert data['total_size'] == 7
    features = data['features']
    assert features[1]['properties']['street_address'] == '1769 FRANKFORD AVE APT 1'
    assert features[1]['match_type'] == 'in_range_unit_child'

def test_addresses_with_unit_and_unmatching_high_num_resolves_to_match_with_no_high_num(client):
    response = client.get('/search/1769-75 frankford ave apt 4')
    data = json.loads(response.get_data().decode())
    assert data['total_size'] == 1
    features = data['features']
    assert features[0]['properties']['street_address'] == '1769 FRANKFORD AVE APT 4'
    assert features[0]['match_type'] == 'in_range'

def test_sort_order_for_address_low_suffix_in_response(client):
    response = client.get('/search/1801 jfk blvd')
    data = json.loads(response.get_data().decode())
    assert data['total_size'] == 2
    features = data['features']
    assert features[0]['properties']['street_address'] == '1801 JOHN F KENNEDY BLVD'
    assert features[1]['properties']['street_address'] == '1801S JOHN F KENNEDY BLVD'

def test_child_addresses_get_linked_address_tags(client):
    response = client.get('/search/621 REED ST APT 2R')
    data = json.loads(response.get_data().decode())
    features = data['features']
    assert features[0]['properties']['dor_parcel_id'] == '009S190092'

def test_match_type_for_search_by_key(client):
    response = client.get('/search/009S190092')
    data = json.loads(response.get_data().decode())
    # assert data['total_size'] == 7 # Skip while query keys only return source address match
    features = data['features']
    assert features[0]['properties']['street_address'] == '621-25 REED ST'
    assert features[0]['match_type'] == 'exact_key'

def test_ranged_addresses_have_linked_tags_from_overlapping(client):
    response = client.get('/search/921-29 E LYCOMING ST?source_details')
    data = json.loads(response.get_data().decode())
    features = data['features']
    assert features[0]['properties']['opa_account_num'][0]['source'] == '921-29 E LYCOMING ST overlaps 921-39 E LYCOMING ST'

def test_overlap_link_respects_parity(client):
    response = client.get('/search/1834-48 BLAIR ST')
    data = json.loads(response.get_data().decode())
    features = data['features']
    assert features[0]['properties']['dor_parcel_id'] == ''

def test_related_addresses_returned_with_include_units(client):
    response = client.get('/search/1708%20chestnut%20st?include_units')
    data = json.loads(response.get_data().decode())
    assert data['total_size'] == 4
    features = data['features']
    assert features[0]['properties']['street_address'] == '1708 CHESTNUT ST'
    assert features[0]['match_type'] == 'exact'
    assert features[1]['properties']['street_address'] == '1708-14 CHESTNUT ST # A'
    assert features[1]['match_type'] == 'range_parent_unit_child'

def test_ranged_address_returns_related_addresses_with_includes_units(client):
    response = client.get('/search/1708-14%20chestnut%20st?include_units')
    data = json.loads(response.get_data().decode())
    assert data['total_size'] == 4
    features = data['features']
    assert features[0]['properties']['street_address'] == '1708-14 CHESTNUT ST'
    assert features[0]['match_type'] == 'exact'
    assert features[1]['properties']['street_address'] == '1708-14 CHESTNUT ST # A'
    assert features[1]['match_type'] == 'unit_child'

def test_ranged_addresses_with_unmatched_unit_returns_correct_match_types(client):
    response = client.get('/search/826-28 N 3rd St Floor 1')
    data = json.loads(response.get_data().decode())
    features = data['features']
    assert features[0]['properties']['street_address'] == '826-28 N 3RD ST'
    assert features[0]['match_type'] == 'has_base'
    assert features[1]['properties']['street_address'] == '826-30 N 3RD ST'
    assert features[1]['match_type'] == 'has_base_overlaps'
    assert features[2]['properties']['street_address'] == '826-34 N 3RD ST'
    assert features[2]['match_type'] == 'has_base_overlaps'
    assert features[3]['properties']['street_address'] == '826 N 3RD ST'
    assert features[3]['match_type'] == 'has_base_in_range'

def test_api_response_signature(client):
    response = client.get('/search/1234 market st')
    data = json.loads(response.get_data().decode())
    assert isinstance(data['search_type'], str)
    assert isinstance(data['search_params'], dict)
    assert isinstance(data['query'], str)
    assert isinstance(data['normalized'], str)
    assert isinstance(data['page'], int)
    assert isinstance(data['page_count'], int)
    assert isinstance(data['page_size'], int)
    assert isinstance(data['total_size'], int)
    assert isinstance(data['type'], str)
    features = data['features']
    assert isinstance(features, list)
    feature = data['features'][0]
    assert isinstance(feature['type'], str)
    assert isinstance(feature['ais_feature_type'], str)
    assert isinstance(feature['match_type'], str)
    assert isinstance(feature['properties'], dict)
    assert isinstance(feature['properties']['street_address'], str)
    assert isinstance(feature['properties']['address_low'], int)
    assert isinstance(feature['properties']['address_low_suffix'], str)
    assert isinstance(feature['properties']['address_low_frac'], str)
    assert isinstance(feature['properties']['address_high'], (int)) if feature['properties']['address_high'] else None == None
    assert isinstance(feature['properties']['street_predir'], str)
    assert isinstance(feature['properties']['street_name'], str)
    assert isinstance(feature['properties']['street_suffix'], str)
    assert isinstance(feature['properties']['street_postdir'], str)
    assert isinstance(feature['properties']['unit_type'], str)
    assert isinstance(feature['properties']['unit_num'], str)
    assert isinstance(feature['properties']['street_full'], str)
    assert isinstance(feature['properties']['street_code'], int)
    assert isinstance(feature['properties']['seg_id'], int)
    assert isinstance(feature['properties']['zip_code'], str)
    assert isinstance(feature['properties']['zip_4'], str)
    assert isinstance(feature['properties']['usps_bldgfirm'], str)
    assert isinstance(feature['properties']['usps_type'], str)
    assert isinstance(feature['properties']['election_block_id'], str)
    assert isinstance(feature['properties']['election_precinct'], str)
    assert isinstance(feature['properties']['pwd_parcel_id'], str)
    assert isinstance(feature['properties']['dor_parcel_id'], str)
    assert isinstance(feature['properties']['li_address_key'], str)
    assert isinstance(feature['properties']['eclipse_location_id'], str)
    assert isinstance(feature['properties']['bin'], str)
    assert isinstance(feature['properties']['pwd_account_nums'], list)
    assert isinstance(feature['properties']['opa_account_num'], str)
    assert isinstance(feature['properties']['opa_owners'], list)
    assert isinstance(feature['properties']['opa_address'], str)
    assert isinstance(feature['properties']['center_city_district'], str)
    assert isinstance(feature['properties']['cua_zone'], str)
    assert isinstance(feature['properties']['li_district'], str)
    assert isinstance(feature['properties']['philly_rising_area'], str)
    assert isinstance(feature['properties']['census_tract_2010'], str)
    assert isinstance(feature['properties']['census_block_group_2010'], str)
    assert isinstance(feature['properties']['council_district_2016'], str)
    assert isinstance(feature['properties']['political_ward'], str)
    assert isinstance(feature['properties']['political_division'], str)
    assert isinstance(feature['properties']['planning_district'], str)
    assert isinstance(feature['properties']['elementary_school'], str)
    assert isinstance(feature['properties']['middle_school'], str)
    assert isinstance(feature['properties']['high_school'], str)
    assert isinstance(feature['properties']['zoning'], str)
    assert isinstance(feature['properties']['zoning_rco'], str)
    assert isinstance(feature['properties']['zoning_document_ids'], list)
    assert isinstance(feature['properties']['police_division'], str)
    assert isinstance(feature['properties']['police_district'], str)
    assert isinstance(feature['properties']['police_service_area'], str)
    assert isinstance(feature['properties']['rubbish_recycle_day'], str)
    assert isinstance(feature['properties']['recycling_diversion_rate'], float)
    assert isinstance(feature['properties']['leaf_collection_area'], str)
    assert isinstance(feature['properties']['sanitation_area'], str)
    assert isinstance(feature['properties']['sanitation_district'], str)
    assert isinstance(feature['properties']['historic_street'], str)
    assert isinstance(feature['properties']['highway_district'], str)
    assert isinstance(feature['properties']['highway_section'], str)
    assert isinstance(feature['properties']['highway_subsection'], str)
    assert isinstance(feature['properties']['traffic_district'], str)
    assert isinstance(feature['properties']['traffic_pm_district'], str)
    assert isinstance(feature['properties']['street_light_route'], str)
    assert isinstance(feature['properties']['pwd_maint_district'], str)
    assert isinstance(feature['properties']['pwd_pressure_district'], str)
    assert isinstance(feature['properties']['pwd_treatment_plant'], str)
    assert isinstance(feature['properties']['pwd_water_plate'], str)
    assert isinstance(feature['properties']['pwd_center_city_district'], str)
    assert isinstance(feature['geometry'], dict)
    assert isinstance(feature['geometry']['geocode_type'], str)
    assert isinstance(feature['geometry']['type'], str)
    assert isinstance(feature['geometry']['coordinates'], list)

def test_reverse_geocode(client):
    response = client.get('/search/-75.15311665258051,39.94923709403044')
    data = json.loads(response.get_data().decode())
    features = data['features']
    assert features[0]['properties']['street_address'] == '714 CHESTNUT ST'
    response = client.get('/search/-75.15311665258051 39.94923709403044')
    data = json.loads(response.get_data().decode())
    features = data['features']
    assert features[0]['properties']['street_address'] == '714 CHESTNUT ST'
    response = client.get('/search/-70 40')
    assert_status(response, 404)
    response = client.get('/search/-70/40')
    assert_status(response, 404)

def test_0_address_low_addresses_return_404(client):
    response = client.get('/addresses/0 Lister')
    assert_status(response, 404)

def test_dor_parcel_search_works_for_multiples_in_address_summary(client):
    response = client.get('/search/016S080346')
    assert_status(response, 200)

def test_block_search_includes_all_opa_addresses(client):
    response = client.get('/block/2400 block of east york st?include_units&opa_only')
    data = json.loads(response.get_data().decode())
    assert data['page_size'] == 27

def test_address_low_suffix_include_units_matches_on_base(client):
    response = client.get('/search/742R S DARIEN ST?include_units')
    data = json.loads(response.get_data().decode())
    assert data['page_size'] == 4
    assert data['features'][0]['match_type'] == 'exact'
    assert data['features'][1]['match_type'] == 'unit_child'
    assert data['features'][1]['properties']['street_address'] == '742R S DARIEN ST # 1'

def test_address_low_suffix_include_units_matches_on_base_for_ranged_address(client):
    response = client.get('/search/5431R-39 westford rd?include_units')
    data = json.loads(response.get_data().decode())
    assert data['page_size'] == 7
    assert data['features'][0]['match_type'] == 'exact'
    assert data['features'][1]['match_type'] == 'unit_child'
    assert data['features'][1]['properties']['street_address'] == '5431R-39 WESTFORD RD # A'

def test_match_type_has_base_no_suffix_unit_child(client):
    pass
    #TODO: find appropriate test case (i.e. 742 S Darien St?include_units) and write test
