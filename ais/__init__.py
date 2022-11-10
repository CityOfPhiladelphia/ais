from flask import Flask
#import flask_cachecontrol
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
# from flasgger import Swagger, MK_SANITIZER

# Flask 2.0
from flask.cli import FlaskGroup


# below fixes "ModuleNotFoundError: No module named 'flask._compat'" error that happens
# in later 2.0 flask versions
#from flask_login._compat import text_type


# Create app instance
app = Flask('__name__', instance_relative_config=True)

# Allow cross-origin requests
CORS(app)

# Allow caching of responses
#FlaskCacheControl(app)

# Load default config
app.config.from_object('config')

# Patch config with instance values
app.config.from_pyfile('config.py')

# Add profiler to app, if configured
if app.config.get('PROFILE', False):
    from werkzeug.contrib.profiler import ProfilerMiddleware
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

if app.config.get('SENTRY_DSN', None):
    from raven.contrib.flask import Sentry
    sentry = Sentry(app, dsn=app.config['SENTRY_DSN'])

# Init database extension
app_db = SQLAlchemy(app)

# Init migration extension
migrate = Migrate(app, app_db)

# # Swaggerify App
# Swagger(app, sanitizer=MK_SANITIZER)
