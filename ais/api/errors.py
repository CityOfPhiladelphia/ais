import json
from collections import OrderedDict


STATUS_CODES = {
    400: 'Bad Request',
    404: 'Not Found',
}

def json_error(status, message, details={}):
    error_data = OrderedDict([
        ('error', STATUS_CODES[status]),
        ('message', message),
        ('details', details),
    ])
    return json.dumps(error_data)