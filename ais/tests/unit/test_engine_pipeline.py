"""Unit tests for the engine build pipeline and refactored geometry/link helpers."""

import importlib
import pytest
from shapely.geometry import LineString, MultiLineString, Point

from ais import app
from ais.engine import pipeline
from ais.engine.scripts.geocode_addresses import _extract_xsect_coord
from ais.engine.scripts.load_addresses import (
    FastAddress,
    _chunk_list,
    build_fast_address,
    extract_parser_tags,
)
from ais.engine.scripts.make_linked_tags import _has_conflicting_parcel_geocodes
from ais.engine.scripts.make_service_area_summary import _build_layer_select_expr
from ais.models import Address


def test_pipeline_steps_are_unique_and_importable():
    """Every step in PIPELINE must have a unique name and resolve to a module with main()."""
    names = [s.name for s in pipeline.PIPELINE]
    assert len(names) == len(set(names))
    assert len(names) == 17

    for name in names:
        mod = importlib.import_module(f"ais.engine.scripts.{name}")
        assert callable(getattr(mod, "main", None)), f"{name} missing main()"


def test_run_pipeline_filtering_and_validation(monkeypatch):
    """Verify --stage, --only, and --from slice selection and invalid-input errors."""
    executed = []
    monkeypatch.setattr(pipeline, "run_step", lambda name: executed.append(name) or 0.01)

    pipeline.run_pipeline(stage="summaries")
    assert executed == ["make_address_summary", "load_service_areas", "make_service_area_summary"]

    executed.clear()
    pipeline.run_pipeline(only_steps=["load_streets", "load_curbs"])
    assert executed == ["load_streets", "load_curbs"]

    executed.clear()
    pipeline.run_pipeline(from_step="load_service_areas")
    assert executed == ["load_service_areas", "make_service_area_summary"]

    with pytest.raises(ValueError, match="Unknown stage"):
        pipeline.run_pipeline(stage="nonexistent")
    with pytest.raises(ValueError, match="Unknown step"):
        pipeline.run_pipeline(only_steps=["not_a_step"])
    with pytest.raises(ValueError, match="Unknown --from step"):
        pipeline.run_pipeline(from_step="not_a_step")


def test_extract_xsect_coord_shapely_2_compat():
    """Verify Shapely 2.x LineString and MultiLineString coordinate extraction."""
    ls = LineString([(0, 0), (10, 20)])
    assert _extract_xsect_coord(ls) == (10.0, 20.0)

    mls = MultiLineString([[(0, 0), (1, 1)], [(2, 2), (30, 40)]])
    assert _extract_xsect_coord(mls) == (30.0, 40.0)

    # Non-line geometries return None safely
    assert _extract_xsect_coord(Point(1, 2)) is None


def test_has_conflicting_parcel_geocodes():
    """Conflicting links require BOTH pwd and dor parcel geoms to differ."""
    gmap = {
        "A": ["POINT(1 1)", "POINT(2 2)"],
        "B": ["POINT(9 9)", "POINT(8 8)"],
        "C": ["POINT(1 1)", "POINT(8 8)"],
    }
    assert _has_conflicting_parcel_geocodes("A", "B", gmap) is True
    assert _has_conflicting_parcel_geocodes("A", "C", gmap) is False
    assert _has_conflicting_parcel_geocodes("A", "MISSING", gmap) is False


@pytest.mark.parametrize(
    "raw_address",
    [
        "1234 MARKET ST",
        "1234-36 MARKET ST",
        "902 PINE ST APT 2R",
        "902 PINE ST # 2R",
        "100 S BROAD ST FL 11 STE 1100",
        "1003R-07 MARKET ST",
        "1234 1/2 MARKET ST",
        "2-6 S 2ND ST",
    ],
)
def test_fast_address_matches_orm_address(raw_address):
    """FastAddress must produce identical fields and derived properties to Address."""
    parser = app.config["PARSER"]()
    parsed = parser.parse(raw_address)

    orm_addr = Address(parsed)
    fast_addr = build_fast_address(parsed)

    assert isinstance(fast_addr, FastAddress)
    assert fast_addr.as_dict() == dict(orm_addr)
    assert fast_addr.parity == orm_addr.parity
    assert fast_addr.address_full == orm_addr.address_full
    assert fast_addr.address_full_num == orm_addr.address_full_num
    assert fast_addr.base_address_no_suffix == orm_addr.base_address_no_suffix
    assert fast_addr.is_base == orm_addr.is_base
    assert fast_addr.generic_unit == orm_addr.generic_unit
    assert fast_addr.hundred_block == orm_addr.hundred_block
    assert fast_addr.unit_full == orm_addr.unit_full


def test_build_fast_address_errors_and_parser_tags():
    """Verify error reasons and parser tag extraction (skipping range addresses)."""
    parser = app.config["PARSER"]()
    parser_tags_items = tuple(
        (k, tuple(v)) for k, v in app.config["ADDRESSES"]["parser_tags"].items()
    )

    none_parsed = {"type": "none", "components": {}}
    assert build_fast_address(none_parsed, distinguish_none_type=True) == "Unknown address type"
    assert build_fast_address(none_parsed, distinguish_none_type=False) == "Not an address"

    single_parsed = parser.parse("1234 MARKET ST")
    tags = extract_parser_tags(single_parsed, parser_tags_items)
    assert any(k == "usps_zipcode" and v == "19107" for _, k, v in tags)

    range_type_parsed = {
        "type": "address",
        "components": {
            "output_address": "1200-98 MARKET ST",
            "address": {"addrnum_type": "Range"},
            "mailing": {"zipcode": "19107", "zip4": None, "uspstype": None, "bldgfirm": None},
            "election": {"blockid": None, "precinct": None},
        },
    }
    assert extract_parser_tags(range_type_parsed, parser_tags_items) == []


def test_chunk_list_preserves_order_and_elements():
    items = [str(i) for i in range(10)]
    chunks = _chunk_list(items, 3)
    assert [len(c) for c in chunks] == [4, 3, 3]
    assert [x for c in chunks for x in c] == items
    assert _chunk_list([], 4) == []


def test_service_area_layer_select_expr_precedence():
    """Verify inline SQL expression precedence matches original multi-UPDATE order."""
    layers = {d["layer_id"]: d for d in app.config["SERVICE_AREAS"]["layers"]}

    # Polygon-only
    assert _build_layer_select_expr(layers["center_city_district"]) == (
        'COALESCE(pt."center_city_district", \'\')'
    )
    # Polygon overridden by non-empty line_single
    assert _build_layer_select_expr(layers["rubbish_recycle_day"]) == (
        'COALESCE(NULLIF(seg."rubbish_recycle_day", \'\'), pt."rubbish_recycle_day", \'\')'
    )
    # Polygon overridden by non-empty line_dual (side-aware)
    assert _build_layer_select_expr(layers["zip_code"]) == (
        'COALESCE(NULLIF(CASE WHEN ads.seg_side = \'L\' THEN seg."zip_code__L" '
        'ELSE seg."zip_code__R" END, \'\'), pt."zip_code", \'\')'
    )
    # Nearest point (KNN)
    assert _build_layer_select_expr(layers["sanitation_convenience_center"]) == (
        'COALESCE(knn."sanitation_convenience_center", \'\')'
    )
    # seg_id point with yes_or_no normalization
    assert _build_layer_select_expr(layers["clean_philly_block_captain"]) == (
        'CASE WHEN COALESCE(NULLIF(seg."clean_philly_block_captain__pt", \'\'), \'\') '
        "!= '' THEN 'Yes' ELSE 'No' END"
    )
    # Polygon with yes_or_no normalization
    assert _build_layer_select_expr(layers["historic_site"]) == (
        'CASE WHEN COALESCE(pt."historic_site", \'\') != \'\' THEN \'Yes\' ELSE \'No\' END'
    )
