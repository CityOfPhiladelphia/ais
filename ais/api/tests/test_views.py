import json
import pytest
from ais import app
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
    response = client.get('/addresses/524 N Broad St')
    assert_status(response, 404)

def test_ranged_address_has_units_with_base_first(client):
    response = client.get('/addresses/1801-23 N 10th St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1, op=gt)

    feature = data['features'][0]
    assert_attr(feature, 'street_address', '1801-23 N 10TH ST')


def test_base_address_has_units_with_base_first(client):
    response = client.get('/addresses/1801 N 10th St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1, op=gt)

    feature = data['features'][0]
    assert_attr(feature, 'street_address', '1801 N 10TH ST')
    assert_opa_address(feature, '1801-23 N 10TH ST')

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

def test_unit_address_in_db(client):
    response = client.get('/addresses/826-28 N 3rd St # 1')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '826-28 N 3RD ST # 1')

def test_unit_address_not_in_db(client):
    response = client.get('/addresses/826-28 N 3rd St # 11')
    assert_status(response, 404)

def test_synounymous_unit_types_found(client):
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
    response = client.get('/addresses/826-28 N 3rd St Suite 1')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)

    feature = data['features'][0]
    assert_opa_address(feature, '826-28 N 3RD ST # 1')

def test_nonsynonymous_unit_types_not_used(client):
    response = client.get('/addresses/826-28 N 3rd St Floor 1')
    assert_status(response, 404)

def test_filter_for_only_opa_addresses(client):
    response = client.get('/addresses/1801 N 10th St?opa_only')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1)
