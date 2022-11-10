#!/bin/bash
cd /ais
source env/bin/activate

# This line has flask serve out the app directly, only for staging
#python application.py runserver -h 0.0.0.0 -p 80

# Create the configuration file that points ais at it's ais_engine database.
echo "SQLALCHEMY_DATABASE_URI = \
    'postgresql://ais_engine:$ENGINE_DB_PASS@$ENGINE_DB_HOST:5432/ais_engine'" > /ais/instance/config.py

# Run nginx as proxy server to gunicorn
# running like this will start in the background
nginx

# Gunicorn will be behind nginx, run on socket. Gunicorn must be run in the /ais folder.
#gunicorn application --bind unix:/tmp/gunicorn.sock --worker-class=gevent --access-logfile '-' --log-level 'debug'
#gunicorn application --bind unix:/tmp/gunicorn.sock --workers 4 --worker-class=gevent --access-logfile '-' --log-level 'notice'
#gunicorn application --bind 0.0.0.0:8080 --workers 5 --threads 2 --worker-class gevent --access-logfile '-' --log-level 'notice'
gunicorn application --bind unix:/tmp/gunicorn.sock --workers 4 --worker-class gevent --access-logfile '-' --log-level 'notice'

