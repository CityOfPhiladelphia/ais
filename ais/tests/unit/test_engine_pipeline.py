"""Unit tests for the engine build pipeline and refactored geometry/link helpers."""

import importlib
import pytest
from shapely.geometry import LineString, MultiLineString, Point

from ais.engine import pipeline
from ais.engine.scripts.geocode_addresses import _extract_xsect_coord
from ais.engine.scripts.make_linked_tags import _has_conflicting_parcel_geocodes


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
