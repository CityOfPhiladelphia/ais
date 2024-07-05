import click
import importlib

@click.command()
@click.option('-s', '--script', default=None)
def engine(script):
    if script:
        print(f'Calling AIS engine script: {script}')
        script = script.replace('.py','')
        # dynamically pull in engine scripts as a module and call their main function
        # The __init__.py in the ais/engine/scripts folder sets all the .py files
        # in that directory to be importable.
        mod = __import__("ais.engine.scripts.{}".format(script), fromlist=["main"])
        mod.main()
    if not script:
        print('Please pass an arg to the --script flag.')

