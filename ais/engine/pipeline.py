"""Declarative AIS engine build pipeline.

Replaces the legacy bash script (`build_engine.sh`) with a structured,
resumable Python runner that logs per-step timing and can run the full
build or any subset of steps.
"""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class BuildStep:
    name: str
    stage: str
    description: str


PIPELINE: tuple[BuildStep, ...] = (
    # Stage 1: Base reference layers
    BuildStep("load_streets", "base_data", "Load street centerlines"),
    BuildStep("load_street_aliases", "base_data", "Load street aliases"),
    BuildStep("make_street_intersections", "base_data", "Build street intersections"),
    BuildStep("load_opa_properties", "base_data", "Load OPA property accounts"),
    BuildStep("load_opa_account_changes", "base_data", "Load OPA account number change map"),
    BuildStep("load_ng911_address_points", "base_data", "Load NG911 site address points"),
    BuildStep("load_dor_parcels", "base_data", "Load DOR parcels"),
    BuildStep("load_dor_condos", "base_data", "Load DOR condominiums"),
    BuildStep("load_pwd_parcels", "base_data", "Load PWD parcels"),
    BuildStep("load_curbs", "base_data", "Load curb polygons"),
    # Stage 2: Address ingestion & linking
    BuildStep("load_addresses", "addresses", "Parse, standardize, and link all address sources"),
    # Stage 3: Geocoding & tag propagation
    BuildStep("geocode_addresses", "geocoding", "Geocode addresses against parcels, NG911, and streets"),
    BuildStep("make_linked_tags", "geocoding", "Propagate tags across linked addresses"),
    BuildStep("geocode_addresses_from_links", "geocoding", "Backfill geocodes via address links"),
    # Stage 4: Denormalized API summary tables
    BuildStep("make_address_summary", "summaries", "Build denormalized address_summary table"),
    BuildStep("load_service_areas", "summaries", "Load service area polygons, lines, and points"),
    BuildStep("make_service_area_summary", "summaries", "Build service_area_summary via PostGIS spatial join"),
)

STEP_NAMES: tuple[str, ...] = tuple(step.name for step in PIPELINE)


def run_step(step_name: str) -> float:
    """Import and execute a single engine script's `main()`, returning elapsed seconds."""
    module_name = step_name.removesuffix(".py")
    print(f"\n{'=' * 78}")
    print(f"[AIS Engine] Running step: {module_name}")
    print(f"{'=' * 78}", flush=True)

    t0 = time.monotonic()
    mod = importlib.import_module(f"ais.engine.scripts.{module_name}")
    mod.main()
    elapsed = time.monotonic() - t0
    print(f"[AIS Engine] Completed '{module_name}' in {timedelta(seconds=int(elapsed))}", flush=True)
    return elapsed


def run_pipeline(
    *,
    from_step: str | None = None,
    only_steps: list[str] | None = None,
    stage: str | None = None,
) -> None:
    """Run all or a selected subset of the engine build pipeline."""
    steps = list(PIPELINE)

    if stage:
        steps = [s for s in steps if s.stage == stage]
        if not steps:
            valid_stages = sorted({s.stage for s in PIPELINE})
            raise ValueError(f"Unknown stage '{stage}'. Valid stages: {', '.join(valid_stages)}")

    if only_steps:
        unknown = [name for name in only_steps if name not in STEP_NAMES]
        if unknown:
            raise ValueError(f"Unknown step(s): {', '.join(unknown)}")
        only_set = set(only_steps)
        steps = [s for s in steps if s.name in only_set]

    if from_step:
        if from_step not in STEP_NAMES:
            raise ValueError(f"Unknown --from step '{from_step}'. Valid steps: {', '.join(STEP_NAMES)}")
        idx = next(i for i, s in enumerate(steps) if s.name == from_step)
        steps = steps[idx:]

    total_start = time.monotonic()
    timings: list[tuple[str, float]] = []

    print(f"[AIS Engine] Starting build pipeline ({len(steps)} step(s))...", flush=True)
    for step in steps:
        elapsed = run_step(step.name)
        timings.append((step.name, elapsed))

    total_elapsed = time.monotonic() - total_start
    print(f"\n{'=' * 78}")
    print(f"[AIS Engine] Pipeline finished in {timedelta(seconds=int(total_elapsed))}")
    for name, sec in timings:
        print(f"  - {name:<32} {timedelta(seconds=int(sec))}")
    print(f"{'=' * 78}", flush=True)
