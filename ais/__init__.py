import os
import click
from flask import Flask
#import flask_cachecontrol
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
# from flasgger import Swagger, MK_SANITIZER

# Flask 2.0
#from flask.cli import AppGroup


# below fixes "ModuleNotFoundError: No module named 'flask._compat'" error that happens
# in later 2.0 flask versions
#from flask_login._compat import text_type


# Create app instance
# Load default config from the instance/config.py folder
app = Flask('__name__', instance_relative_config=True)
# Patch config with instance values
app.config.from_pyfile('/ais/config.py')

# Synthesize our database connection from passing vars
db_host = os.environ['ENGINE_DB_HOST']
db_pass = os.environ['ENGINE_DB_PASS']
# format is: "postgresql://postgres:postgres@localhost/DBNAME"
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://ais_engine:{db_pass}@{db_host}/ais_engine'
# Init database extension
app_db = SQLAlchemy(app)

# Allow cross-origin requests
CORS(app)

# Allow caching of responses
#FlaskCacheControl(app)

# Add profiler to app, if configured
if app.config.get('PROFILE', False):
    from werkzeug.contrib.profiler import ProfilerMiddleware
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

if app.config.get('SENTRY_DSN', None):
    from raven.contrib.flask import Sentry
    sentry = Sentry(app, dsn=app.config['SENTRY_DSN'])

# Init migration extension
migrate = Migrate(app, app_db)


