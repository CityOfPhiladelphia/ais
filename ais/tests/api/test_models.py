import json
import pytest
from ais import app, app_db, models
from operator import eq, gt

@pytest.mark.skip(reason="Ofc feature doesn't return with new version - find another example")
def test_no_unit_sorted_first():
    """
    e.g., 2401 Pennsylvania Ave Ofc should never precede 2401 Pennsylvania Ave.
    """
    addresses = models.AddressSummary.query.filter_by(
            address_low=2401,
            street_name='PENNSYLVANIA',
            street_suffix='AVE',
            address_high=None,
            unit_num=''
        )\
        .order_by_address()

    num_addresses = addresses.count()
    assert num_addresses >= 2, 'Len addresses is {}'.format(num_addresses)

    first_address = addresses[0]
    assert not first_address.unit_type, 'First has a unit_type: {}'.format(first_address.unit_type)
    assert not first_address.unit_num, 'First has a unit_num: {}'.format(first_address.unit_num)
