"""Unit tests for AIS ORM models, Address parsing helpers, and mapper hygiene."""

import warnings
import pytest
from sqlalchemy.orm import configure_mappers

from ais.models import Address


def test_mappers_configure_without_warnings():
    """All read-only ORM relationships should configure cleanly with no SAWarnings."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        configure_mappers()
    sa_warnings = [w for w in caught if "SAWarning" in w.category.__name__]
    assert sa_warnings == [], [str(w.message) for w in sa_warnings]


def test_address_parsing_and_properties():
    """Verify standardized components and computed properties for a standard address."""
    addr = Address("1234 Market St")
    assert addr.street_address == "1234 MARKET ST"
    assert addr.address_low == 1234
    assert addr.address_high is None
    assert addr.street_name == "MARKET"
    assert addr.street_suffix == "ST"
    assert addr.parity == "E"
    assert addr.hundred_block == 1200
    assert addr.is_base is True
    assert addr.is_basic_range is False
    assert addr.child_nums == []


def test_ranged_address_child_nums():
    """Basic ranged addresses expand by parity into individual child numbers."""
    addr = Address("919-23 S 7th St")
    assert addr.is_basic_range is True
    assert addr.parity == "O"
    assert addr.child_nums == [919, 921, 923]
    assert addr.address_full == "919-23"


def test_unit_address_properties():
    """Unit addresses expose generic `#` formatting and non-base status."""
    addr = Address("600 S 48th St Apt 2B")
    assert addr.is_base is False
    assert addr.unit_type == "APT"
    assert addr.unit_num == "2B"
    assert addr.unit_full == "APT 2B"
    assert addr.generic_unit == "600 S 48TH ST # 2B"


def test_invalid_address_raises_value_error():
    """Unparseable strings and non-address inputs raise ValueError."""
    with pytest.raises(ValueError):
        Address("not a valid address")
    with pytest.raises(ValueError):
        Address(12345)
