"""Top-level `ais` console script."""

import click
from ais.engine.commands import engine


@click.group()
def cli():
    """AIS command-line interface."""


cli.add_command(engine)
