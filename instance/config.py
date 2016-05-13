"""
PUT YOUR PRIVATE CONFIGURATION IN ENVIRONMENT VARIABLES! Put instance-specific
stuff in here. These override the settings in the main config.py.

See: https://exploreflask.com/configuration.html
"""

import os
SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')

# Suppress some weird warning.
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = True

from passyunk.parser import PassyunkParser
PARSER = PassyunkParser

DATABASES = {
    'engine':   os.environ.get('ENGINE_DATABASE'),
    'api':      os.environ.get('API_DATABASE'),

    'gisdbp':   os.environ.get('GISDBP_DATABASE'),
    'brtprod':  os.environ.get('BRTPROD_DATABASE'),
}

DEBUG = (os.environ.get('PROFILE', 'False').title() == 'True')
PROFILE = (os.environ.get('PROFILE', 'False').title() == 'True')

BASE_DATA_SOURCES = {
    'streets': {
        'db':               'gisdbp',
        'table':            'GIS_STREETS.Street_Centerline',
        # 'srid':             2272,
        # 'geom_field':       'shape',
        'field_map':  {
            'seg_id':                   'seg_id',
            'street_code':              'st_code',
            'left_from':                'l_f_add',
            'left_to':                  'l_t_add',
            'right_from':               'r_f_add',
            'right_to':                 'r_t_add',
            'street_predir':            'pre_dir',
            'street_name':              'st_name',
            'street_suffix':            'st_type',
            'street_postdir':           'suf_dir',
        }
    },
    'street_aliases': {
        'db':               'gisdbp',
        'table':            'GIS_STREETS.alias_list',
        'field_map': {
            'seg_id':                   'seg_id',
            'street_predir':            'pre_dir',
            'street_name':              'name',
            'street_suffix':            'type',
            'street_postdir':           'suf_dir',
        },
    },
    'parcels': {
        'pwd': {
            'db':               'gisdbp',
            'table':            'GIS_WATER.PWD_Parcels',
            'field_map': {
                'parcel_id':            'parcelid',
                'source_address':       'address',
                'source_brt_id':        'brt_id',
            },
        },
        'dor': {
            'db':               'gisdbp',
            'table':            'GIS_DOR.PARCEL',
            'field_map': {
                'source_object_id':     'objectid',
                'parcel_id':            'mapreg',
                'street_code':          'stcod',
                'address_low':          'house',
                'address_low_suffix':   'suf',
                'address_high':         'stex',
                'street_predir':        'stdir',
                'street_name':          'stnam',
                'street_suffix':        'stdes',
                'street_postdir':       'stdessuf',
                'unit_num':             'unit'
            },
            # Query only active parcels
            'where':            'status in (1, 3)',
        },
    },
    'properties': {
        'db':               'brtprod',
        'table':            'brt_admin.properties',
        'field_map': {
            'account_num':          'parcelno',
            'tencode':              'propertyid',
            'source_address':       'location',
            'address_suffix':       'suffix',
            'unit':                 'unit',
        },
    },
    'curbs': {
        'db':               'gisdbp',
        'table':            'GIS_STREETS.Curbs_No_Cartways',
        'field_map':  {
            'curb_id':              'cp_id',
            'geom':                 'shape',
        },
    },
    'opa_owners': {
        'db':               'gisdbp',
        'table':            'GIS_AIS_SOURCES.VW_OPA_OWNERS',
        'field_map': {
            'account_num':              'account_num',
            'street_address':           'street_address',
        },
    },
}

ERROR_TABLES = {
    'dor_parcels': {
        'error_table':      'dor_parcel_error',
        'polygon_table':    'dor_parcel_error_polygon',
    },
    'addresses': {
        'error_table':      'address_error',
    },
}
