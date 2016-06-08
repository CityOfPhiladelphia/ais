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

def assert_opa_address(feature, expected_address):
    actual_address = feature['properties']['opa_address']
    assert actual_address == expected_address, (
        'Expected OPA address of {}; received {}.').format(
        expected_address, actual_address)

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
    assert feature['properties']['street_address'] == '1801-23 N 10TH ST'


def test_base_address_has_units_with_base_first(client):
    response = client.get('/addresses/1801 N 10th St')
    assert_status(response, 200)

    data = json.loads(response.get_data().decode())
    assert_num_results(data, 1, op=gt)

    feature = data['features'][0]
    assert feature['properties']['street_address'] == '1801 N 10TH ST'
    assert_opa_address(feature, '1801-23 N 10TH ST')

def test_unit_address_in_db(client):
    assert False

def test_unit_address_not_in_db(client):
    assert False
