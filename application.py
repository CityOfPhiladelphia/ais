# Import ais from our ais/__init__.py file
from ais import app as application
# New flask 2.0 cli
from flask.cli import FlaskGroup

# Importing ais.api will initialize the app's routes.
import ais.api.views
