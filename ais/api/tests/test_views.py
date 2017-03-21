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

@pytest.mark.skip(reason="todo - return OPA full address")
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
            AND (address_link.relationship = 'has base' OR address_link.relationship IS NULL)
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
    assert feature['geometry']['geocode_type'] == 'true range'
    assert feature['match_type'] == 'unmatched'

def test_cascade_to_full_range(client):
    #response = client.get('/search/3551 ashfield lane')
    response = client.get('/search/3419 ashfield lane')
    data = json.loads(response.get_data().decode())
    feature = data['features'][0]
    assert feature['geometry']['geocode_type'] == 'full range'
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
    assert_status(response, 200)
    feature = data['features'][0]
    assert feature['geometry']['geocode_type'] == 'true_range'

def test_address_without_seg_match_returns_404(client):
    response = client.get('/search/2100 SITTY TAWK AVE')
    assert_status(response, 404)


# TESTS for LINKED TAGS CHANGES

def test_addresses_with_unmatching_unit_num_resolves_to_base_address_match(client):
    response = client.get('/search/1769 frankford ave apt 2000')
    assert_status(response, 200)

def test_addresses_with_unmatching_unit_num_resolves_to_base_address_match_with_include_units(client):
    response = client.get('/search/1769 frankford ave apt 2000?include_units')
    data = json.loads(response.get_data().decode())
    assert_status(response, 200)
    assert data['total_size'] == 7
    features = data['features']
    assert features[0]['properties']['street_address'] == '1769 FRANKFORD AVE'
    assert features[1]['properties']['street_address'] == '1769 FRANKFORD AVE APT 1'

def test_addresses_with_unmatching_high_num_resolves_to_match_with_no_high_num(client):
    response = client.get('/search/1769-75 frankford ave')
    assert_status(response, 200)

def test_addresses_with_unmatching_high_num_resolves_to_match_with_no_high_num_with_include_units(client):
    pass

def test_addresses_with_unit_and_unmatching_high_num_resolves_to_match_with_no_high_num(client):
    pass






