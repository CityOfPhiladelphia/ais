from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand


# Create app instance
app = Flask(__name__, instance_relative_config=True)
CORS(app)

# Load default config
app.config.from_object('config')

# Patch config with instance values
app.config.from_pyfile('config.py')

# Add profiler to app, if configured
if app.config.get('PROFILE', False):
    from werkzeug.contrib.profiler import ProfilerMiddleware
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

# Init database extension
app_db = SQLAlchemy(app)

# Init manager and register commands
manager = Manager(app)
manager.add_command('db', MigrateCommand)

# Import engine manager here to avoid circular imports
from ais.engine.manage import manager as engine_manager
manager.add_command('engine', engine_manager)

# Init migration extension
migrate = Migrate(app, app_db)
