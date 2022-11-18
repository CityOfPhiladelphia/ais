# Import ais from our ais/__init__.py file
from ais import app as application
# New flask 2.0 cli
from flask.cli import FlaskGroup

# Importing ais.api will initialize the app's routes.
import ais.api.views

# setup in this wierd way for the benefit of setup.py
def cli_entry():
    cli = FlaskGroup(application)
    cli()

if __name__ == '__main__':
    cli_entry()
