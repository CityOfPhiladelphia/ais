import click
from ais.engine.commands import engine


@click.group()
def cli():
    pass

# for whatever reaosn, setting the console_scripts in setup.py to point
# at this script sets __name__ to this.
if __name__ == 'ais.commands':
    cli.add_command(engine)
    cli()
