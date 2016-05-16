##
# Starting the web service

web: gunicorn application --bind ${IP:-0.0.0.0}:${PORT:-5000} --workers ${WORKERS:-9} --worker-class=gevent
