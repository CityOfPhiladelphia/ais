#!/bin/bash
cd /ais
source env/bin/activate
# This line has flask serve out the app directly, only for staging
#python application.py runserver -h 0.0.0.0 -p 80

# Create the configuration file that points ais at it's ais_engine database.
echo "SQLALCHEMY_DATABASE_URI = \
    'postgresql://ais_engine:$ENGINE_DB_PASS@$ENGINE_DB_HOST:5432/ais_engine'" > /ais/instance/config.py

# Gunicorn is used for production, it must be run in the /ais folder.
#gunicorn application --bind 0.0.0.0:8080 --workers 4 --worker-class=gevent --access-logfile '-'
gunicorn application --bind 0.0.0.0:8080 --worker-class=gevent --access-logfile '-' --log-level 'debug'
