"""Unit tests for spatial, URL, and dict utilities in `ais.util`."""

import pytest
from shapely.geometry import LineString, Point

from ais import util


def test_parity_helpers():
    """Verify odd/even/both/unknown parity calculations."""
    assert util.parity_for_num(100) == "E"
    assert util.parity_for_num(101) == "O"
    assert util.parity_for_range(100, 108) == "E"
    assert util.parity_for_range(101, 109) == "O"
    assert util.parity_for_range(100, 101) == "B"
    assert util.parity_for_range(100, None) == "U"
    assert util.parity_for_range(100, 0) == "U"


def test_parse_url():
    """Parse both postgis:// and postgresql:// URLs with optional ports."""
    parsed = util.parse_url("postgis://ais_engine:secret@db.example.com:5433/ais_engine")
    assert parsed == {
        "scheme": "postgis",
        "host": "db.example.com",
        "port": 5433,
        "user": "ais_engine",
        "password": "secret",
        "db_name": "ais_engine",
    }

    no_port = util.parse_url("postgresql://user:pw@localhost/mydb")
    assert no_port["port"] is None
    assert no_port["db_name"] == "mydb"


def test_redact_url_hides_password():
    """redact_url strips credentials so DB passwords never appear in logs or tracebacks."""
    redacted = util.redact_url("postgis://citygeo:s3cr3tP@ss@db.example.com:5432/databridge")
    assert "s3cr3t" not in redacted
    assert redacted == "postgis://citygeo:***@db.example.com:5432/databridge"

    no_auth = util.redact_url("postgresql://localhost/ais_engine")
    assert no_auth == "postgresql://localhost/ais_engine"


def test_not_none_dict_filters_none_values():
    """NotNoneDict excludes None on init and assignment, and deletes keys set to None."""
    d = util.NotNoneDict(a=1, b=None, c="")
    assert d == {"a": 1, "c": ""}
    d["a"] = None
    assert "a" not in d
    d["d"] = 0
    assert d["d"] == 0


def test_project_shape_round_trip():
    """Projecting City Hall between PA State Plane (2272) and WGS84 (4326) is accurate."""
    # Philadelphia City Hall (~ -75.1636, 39.9524)
    wgs84_pt = Point(-75.1636, 39.9524)
    sp_pt = util.project_shape(wgs84_pt, 4326, 2272)
    assert 2_650_000 < sp_pt.x < 2_750_000
    assert 200_000 < sp_pt.y < 300_000

    round_trip = util.project_shape(sp_pt, 2272, 4326)
    assert round_trip.x == pytest.approx(wgs84_pt.x, abs=1e-5)
    assert round_trip.y == pytest.approx(wgs84_pt.y, abs=1e-5)

    # Same-SRID fast path returns original object without reprojecting
    assert util.project_shape(wgs84_pt, 4326, 4326) is wgs84_pt


def test_interpolate_buffered_and_offset():
    """Verify buffered interpolation and left/right perpendicular offsets."""
    horiz = LineString([(0, 0), (100, 0)])
    mid = util.interpolate_buffered(horiz, 0.5, 10)
    assert mid.x == pytest.approx(50.0)
    assert mid.y == pytest.approx(0.0)

    left_pt = util.offset(horiz, mid, 5, "L")
    right_pt = util.offset(horiz, mid, 5, "R")
    assert left_pt.y == pytest.approx(5.0)
    assert right_pt.y == pytest.approx(-5.0)

    # Vertical line special case
    vert = LineString([(0, 0), (0, 100)])
    v_mid = Point(0, 50)
    assert util.offset(vert, v_mid, 5, "R").x == pytest.approx(5.0)
    assert util.offset(vert, v_mid, 5, "L").x == pytest.approx(-5.0)
