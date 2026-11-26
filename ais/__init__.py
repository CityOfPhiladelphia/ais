"""AIS Flask application initialization."""

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config.from_object("ais.config")

app_db = SQLAlchemy(app)
CORS(app)

if app.config.get("PROFILE", False):
    from werkzeug.middleware.profiler import ProfilerMiddleware

    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])
