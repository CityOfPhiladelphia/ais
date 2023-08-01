import os
from flask import Flask, g
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
import dns.resolver

pardir = os.path.abspath('..')

# load from .env file
try:
    print('Loading the .env file, will use database info if found there...')
    load_dotenv()
except Exception:
    load_dotenv(pardir + '/ais/.env')

# Create app instance
app = Flask('__name__')
# load non-sensitive configurations from config.py
app.config.from_object('config')
# load sensitive configurations from instance/config.py
# Note these will both be imported in app.config so don't have any conflicting values
# in either that will overwrite the other.
# reference "Instance Folders": https://flask.palletsprojects.com/en/2.3.x/config/

# config path will be here if run in our built Docker image
if os.path.isfile('/ais/instance/config.py'):
    print(f'Loading /ais/instance/config.py as our secrets instance config..')
    app.config.from_pyfile('/ais/instance/config.py')
# Otherwise, default to the current working directory which should work when ais is installed as a package locally.
else:
    print(f'Loading {os.getcwd() + "/config.py"} as our secrets instance config..')
    app.config.from_pyfile('instance/config.py')

# config path will be here if run in our built Docker image
if os.path.isfile('/ais/config.py'):
    print(f'Loading /ais/config.py as our Flask config..')
    app.config.from_pyfile('/ais/config.py')
# Otherwise, default to the current working directory which should work when ais is installed as a package locally.
else:
    print(f'Loading {os.getcwd() + "/config.py"} as our Flask config..')
    app.config.from_pyfile(os.getcwd() + '/config.py')

# Synthesize our database connection from env vars if they exist
try:
    db_host = os.environ['ENGINE_DB_HOST']
except Exception as e:
    db_host = None

try:
    db_pass = os.environ['ENGINE_DB_PASS']
except Exception as e:
    db_pass = None

try:
    dev_test = os.environ['DEV_TEST']
except Exception as e:
    dev_test = None

# Figure out 
if db_host is None: # FIX: This should be triggered so switch between them
    try:
        result = dns.resolver.resolve('ais-prod.phila.city')
        prod_cname = result.canonical_name.to_text()
        if dev_test == 'true':
            print('Will attempt to use local build database..')
            db_host = 'localhost'
            db_pass = os.environ['LOCAL_PASSWORD']
        else:
          print('DEV_TEST is false, determining which production database to use..')
          if 'blue' in prod_cname:
              db_host = app.config['BLUE_DATABASE']['host']
              db_pass = app.config['BLUE_DATABASE']['password']
          elif 'green' in prod_cname:
              db_host = app.config['GREEN_DATABASE']['host']
              db_pass = app.config['GREEN_DATABASE']['password']
    except Exception as e:
        print(str(e))

assert db_host != None, 'Could not get host for backend database!'
assert db_pass != None, 'Could not get password for backend database!'
print(f'Prod host chosen: {db_host}')

# Debug print if we got our creds as env variables (necessary for how we run it in docker/ECS)
# format is: "postgresql://postgres:postgres@localhost/DBNAME"
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://ais_engine:{db_pass}@{db_host}/ais_engine'
# Init database extension
app_db = SQLAlchemy(app)

# Close database sessions in case our app is killed.
@app.teardown_appcontext
def teardown_app_context(exception=None):
    db = getattr(g, '_database', None)
    if db is not None:
        db.session.remove()

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
