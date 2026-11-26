"""CLI commands for building and managing the AIS engine database."""

import click
from ais.engine.pipeline import PIPELINE, run_pipeline


@click.group()
def engine():
    """Build and manage AIS engine database tables."""


@engine.command("list")
def list_steps():
    """List all engine build pipeline steps in execution order."""
    current_stage = None
    for idx, step in enumerate(PIPELINE, start=1):
        if step.stage != current_stage:
            current_stage = step.stage
            click.echo(f"\n[{current_stage}]")
        click.echo(f"  {idx:2d}. {step.name:<32} {step.description}")


@engine.command("build")
@click.option("--from", "from_step", default=None, help="Resume pipeline starting at this step name.")
@click.option("--only", default=None, help="Comma-separated list of specific steps to run.")
@click.option(
    "--stage",
    default=None,
    help="Run only steps in a specific stage (base_data, addresses, geocoding, summaries).",
)
def build(from_step: str | None, only: str | None, stage: str | None):
    """Run the AIS engine table build pipeline."""
    only_steps = [s.strip() for s in only.split(",") if s.strip()] if only else None
    run_pipeline(from_step=from_step, only_steps=only_steps, stage=stage)
