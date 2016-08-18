##
# Starting the web service

web: gunicorn application --bind ${IP:-0.0.0.0}:${PORT:-5000} --workers ${WORKERS:-4} --worker-class=${WORKER_CLASS:-gevent}
