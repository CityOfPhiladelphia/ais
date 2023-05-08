import os
import click
from flask import Flask
#import flask_cachecontrol
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
import dns.resolver
#from ais import app
# from flasgger import Swagger, MK_SANITIZER

pardir = os.path.abspath('..')

# load from .env file
try:
    print('Loading the .env file, will use database info if found there...')
    load_dotenv()
except Exception:
    load_dotenv(pardir + '/ais/.env')

# Flask 2.0
#from flask.cli import AppGroup

# Create app instance
app = Flask('__name__')
# load non-sensitive configurations from config.py
app.config.from_object('config')
# load sensitive configurations from instance/config.py
# Note these will both be imported in app.config so don't have any conflicting values
# in either that will overwrite the other.
# reference "Instance Folders": https://flask.palletsprojects.com/en/2.3.x/config/
app.config.from_pyfile('instance/config.py')

# debug print all config options to make sure we're loading them correctly
# will be referenced by script later like a dictionary
#print(app.config)

flask_config_file = os.getcwd() + '/config.py'

if flask_config_file:
    print(f'Loading {flask_config_file} as our Flask config..')
    app.config.from_pyfile(flask_config_file)
else:
    raise FileNotFoundError('Flask configuration file not found! Please make one and place it in the current directory as "config.py".')

# Synthesize our database connection from env vars if they exist
try:
    db_host = os.environ['ENGINE_DB_HOST']
except Exception as e:
    db_host = None

try:
    db_pass = os.environ['ENGINE_DB_PASS']
except Exception as e:
    db_pass = None

# Figure out 
if db_host is None:
    try:
        result = dns.resolver.resolve('ais-prod.phila.city')
        prod_cname = result.canonical_name.to_text()
        if 'blue' in prod_cname:
            db_host = app.config['BLUE_DATABASE']['host']
            db_pass = app.config['BLUE_DATABASE']['password']
        if 'green' in prod_cname:
            db_host = app.config['GREEN_DATABASE']['host']
            db_host = app.config['GREEN_DATABASE']['password']
    except Exception as e:
        print(str(e))

if db_host is None:
    raise AssertionError('Could not get host for backend database!')
if db_pass is None:
    raise AssertionError('Could not get password for backend database!')

print(os.environ['ENGINE_DB_HOST'])
print(os.environ['ENGINE_DB_PASS'])
# format is: "postgresql://postgres:postgres@localhost/DBNAME"
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://ais_engine:{db_pass}@{db_host}/ais_engine'
# Init database extension
app_db = SQLAlchemy(app)

# Allow cross-origin requests
CORS(app)

# Add profiler to app, if configured
if app.config.get('PROFILE', False):
    from werkzeug.contrib.profiler import ProfilerMiddleware
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

if app.config.get('SENTRY_DSN', None):
    from raven.contrib.flask import Sentry
    sentry = Sentry(app, dsn=app.config['SENTRY_DSN'])

# Init migration extension
migrate = Migrate(app, app_db)


