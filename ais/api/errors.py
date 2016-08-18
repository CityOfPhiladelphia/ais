import json
from collections import OrderedDict


STATUS_CODES = {
    400: 'Bad Request',
    404: 'Not Found',
    500: 'Internal Server Error',
}

def json_error(status, message, details={}):
    error_data = OrderedDict([
        ('status', status),
        ('error', STATUS_CODES.get(status, '')),
        ('message', message),
        ('details', details),
    ])
    return json.dumps(error_data)