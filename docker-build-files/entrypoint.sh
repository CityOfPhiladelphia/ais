#!/bin/bash
cd /ais
#source /ais/venv/bin/activate

if [ -z "${ENGINE_DB_PASS}" ]; then
    echo 'ENGINE_DB_PASS var not set!'
    exit 1
fi
if [ -z "${BLUE_ENGINE_CNAME}" ]; then
    echo 'BLUE_ENGINE_CNAME var not set!'
    exit 1
fi
if [ -z "${GREEN_ENGINE_CNAME}" ]; then
    echo 'GREEN_ENGINE_CNAME var not set!'
    exit 1
fi

if [ ! -z "${ENGINE_DB_HOST}" ]; then
    prod_color=$(dig ais-prod.phila.city +short | grep -o "blue\|green")
    if [[ "$PROD_COLOR" -eq "blue" ]]; then
        export ENGINE_DB_HOST=$BLUE_ENGINE_CNAME
    fi
    if [[ "$PROD_COLOR" -eq "green" ]]; then
        export ENGINE_DB_HOST=$GREEN_ENGINE_CNAME
    fi
fi

if [ -z "${ENGINE_DB_HOST}" ]; then
    echo 'ENGINE_DB_HOST var not set!'
    exit 1
fi

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

