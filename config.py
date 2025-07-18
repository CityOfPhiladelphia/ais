import os
import re

SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')
if 'SQLALCHEMY_POOL_SIZE' in os.environ:
    SQLALCHEMY_POOL_SIZE = int(os.environ.get('SQLALCHEMY_POOL_SIZE'))

# Suppress some weird warning.
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = (os.environ.get('SQLALCHEMY_ECHO', 'False').title() == 'True')

from passyunk.parser import PassyunkParser
PARSER = PassyunkParser

#DATABASES = {
    # these are set in instance config or environment variables
#}

DEBUG = (os.environ.get('DEBUG', 'False').title() == 'True')
PROFILE = (os.environ.get('PROFILE', 'False').title() == 'True')
SENTRY_DSN = os.environ.get('SENTRY_DSN', None)

ENGINE_SRID = 2272
DEFAULT_API_SRID = 4326
DEFAULT_SEARCH_RADIUS = 300
MAXIMUM_SEARCH_RADIUS = 10000
DEFAULT_AIS_MAX_RANGE = 0 # How far away an address_low number can be from a valid street range to return an umatched response; overridden by query argument MAX_RANGE=xxx
OWNER_RESPONSE_LIMIT = 999
OWNER_PARTS_THRESHOLD = 10
VALID_ADDRESS_LOW_SUFFIXES = ('F', 'R', 'A', 'S', 'M', 'P', 'G', 'B', 'C', 'D', 'L', 'Q', '2')

BASE_DATA_SOURCES = {
    'streets': {
        'db':               'citygeo',
        'table':            'viewer_streets.street_centerline',
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
        'db':               'citygeo',
        'table':            'viewer_ais_sources.alias_list_ais',
        'field_map': {
            'seg_id':                   'seg_id',
            'street_predir':            'pre_dir',
            'street_name':              'name',
            'street_suffix':            'type_',
            'street_postdir':           'suf_dir',
        },
    },
    'parcels': {
        'pwd': {
            'db':               'citygeo',
            'table':            'viewer_pwd.pwd_parcels',
            'field_map': {
                'parcel_id':            'parcelid',
                'source_address':       'address',
                'source_brt_id':        'brt_id',
            },
        },
        'dor': {
            'db':               'citygeo',
            'table':            'viewer_dor.dor_parcel',
            'field_map': {
                'source_object_id':     'objectid',
                'parcel_id':            'mapreg',
                'street_code':          'stcod',
                'address_low':          'house',
                'address_low_suffix':   'suf',
                'address_low_frac':     'frac',
                'address_high':         'stex',
                'street_predir':        'stdir',
                'street_name':          'stnam',
                'street_suffix':        'stdes',
                'street_postdir':       'stdessuf',
                'unit_num':             'unit',
                'geom':                 'shape',
            },
            # Query only active parcels
            'where':            'status in (1, 3)',
        },
    },
    'condos': {
        'dor': {
            'db':               'citygeo',
            'table':            'viewer_dor.condominium',
            'field_map': {
                'source_object_id':     'objectid',
                'parcel_id':            'mapref',
                'unit_num':             'condounit',
            },
            # Query only active condos
            'where':            'status in (1, 3)',
        }
    },
    'properties': {
        'db':               'citygeo',
        'table':            'citygeo.cama_address_source_for_ais',
        'field_map': {
            'account_num':          'opa_account_num',
            'tencode':              'property_id',
            'source_address':       'street_address',
        },
    },
    'opa_active_accounts': {
        'db':               'citygeo',
        'table':            'viewer_opa.opa_active_accounts',
        'field_map': {
            'account_num':          'opa_act',
            'source_address':       'address',
            'unit_num':             'unit',
            'geom':                 'shape',
        },
    },
    'ng911_address_points': {
        'db':               'citygeo',
        'table':            'viewer_ng911.ng911_siteaddresses',
        'field_map': {
            'source_address':       'street_address',
            'guid':                 'guid',
            'placement_type':       'placement',
            # I think this needs to be explicitly added since shape isn't auto-queried by datum for postgis
            'geom':                 'shape',
        },
        # Query only verified/accepted addresses
        'where':            'status in (0,1)',
    },
    'curbs': {
        'db':               'citygeo',
        'table':            'viewer_streets.curbs_no_cartways',
        'field_map':  {
            'curb_id':              'cp_id',
            'geom':                 'shape',
        },
    },
    'opa_owners': {
        'db':               'citygeo',
        'table':            'citygeo.opa_owners_cama_ais',
        'field_map': {
            'account_num':              'account_num',
            'street_address':           'street_address',
        },
    },
}

def multi_strip(str_):
    return str_.strip(' ').lstrip('0')

# Preprocessor for L&I addresses
# Not using this since Nick is cleaning everything up in the GIS_LNI DB.
# def make_li_address(comps):
#     out_comps = []
#     # Make primary address num.
#     addr_num = multi_strip(comps['address_low'])
#     # Handle address suffixes.
#     suf = comps['address_low_suffix'].strip()
#     if len(suf) > 0:
#         if suf.isnumeric():
#             # Decode fractionals.
#             if suf == '2':
#                 out_comps.append('1/2')
#         elif suf.isalpha():
#             addr_num += suf
#         else: raise ValueError('Unhandled L&I postdir: {}'.format(suf))
#     # Handle address extension.
#     addr_high = comps['address_high']
#     addr_high = addr_high.lstrip('0') if isinstance(addr_high, str) else None
#     addr_num += '-{}'.format(addr_high) if addr_high else ''
#     out_comps.append(addr_num)
#     # Add remaining fields
#     for field_suffix in ['predir', 'name', 'suffix']:
#         out_comps.append(comps['street_' + field_suffix])
#     # Unit
#     unit_num = comps['unit_num']
#     if unit_num and len(multi_strip(unit_num)) > 0:
#         out_comps += ['#', comps['unit_num']]
#     # Filter blanks
#     out_comps = [x for x in out_comps if x and len(multi_strip(x)) > 0]
#     addr = ' '.join(out_comps)
#     return addr

def make_pwd_account_address(comps):
    a = comps['street_address']
    a = re.sub('-R(EAR)?(?= )', 'R', a)
    return a

def make_voter_address(comps):
    low_num = comps['address_low']
    street_name = comps['street_name']
    unit_num = comps['unit_num']
    address_low_suffix = comps['address_low_suffix']
    low_num_full = low_num + address_low_suffix if address_low_suffix else low_num
    low_num_full = low_num_full.replace(" ", "") if low_num_full else low_num_full
    street_address = (low_num_full, street_name)
    street_address = " ".join(filter(None, street_address))
    if not unit_num:
        return street_address
    unit_tokens = unit_num.split()
    if len(unit_tokens) == 1:
        return street_address + ' # ' + unit_num 
    elif len(unit_tokens) >= 2 and unit_tokens[0] in ['APT', 'APT.', 'APART', 'REAR', 'RM', 'ROOM', 'SIDE', 'UNIT']:
        # ['FL', 'FLR', 'FLOOR', 'STE'] will have # sign automatically stripped by passyunk,
        # so they don't need to be explicitly handled.
        return street_address + ' ' + unit_num
    else:
        return street_address + ' # ' + unit_num

def make_voter_name(comps):
    first_name = comps['first_name']
    middle_name = comps['middle_name']
    last_name = comps['last_name']
    name = (first_name, middle_name, last_name)
    return " ".join(filter(None, name))

def make_rtt_address(comps):
    low_num = str(comps['address_low']) if comps['address_low'] else None
    address_low_suffix = comps['address_low_suffix']
    addr_high = comps['address_high']
    addr_high = None if addr_high == '-1' else addr_high
    addr_high = addr_high.lstrip('0') if isinstance(addr_high, str) else None
    addr_num = '{low_num}-{addr_high}'.format(low_num=low_num, addr_high=addr_high) if low_num and addr_high else low_num
    addr_num = addr_num + address_low_suffix if addr_num and address_low_suffix else addr_num
    unit_num = '#' + str(comps['unit_num']) if comps['unit_num'] else None
    street_predir = comps['street_predir']
    street_postdir = comps['street_postdir']
    street_name = comps['street_name']
    street_type = comps['street_type']
    out_comps = (addr_num, street_predir, street_name, street_type, street_postdir, unit_num)
    # Filter blanks
    out_comps = [x for x in out_comps if x and len(multi_strip(x)) > 0]
    addr = ' '.join(out_comps)
    return addr

def make_dor_parcel_id(comps):
    reg_map_id = comps['reg_map_id']
    return reg_map_id.replace('-', '')

def make_eclipse_address(comps):
    base_address = comps['base_address']
    unit_num = comps['unit_num']
    unit_type = comps['unit_type']
    if base_address:
        if unit_num:
            if unit_type:
                return base_address + ' ' + unit_type + ' ' + unit_num
            else:
                return base_address + ' # ' + unit_num
        elif unit_type:
            return base_address + ' ' + unit_type
        else:
            return base_address
    else:
        return None


ADDRESSES = {
    'parser_tags': {

        'usps_zipcode': ['mailing', 'zipcode'],
        'usps_zip4': ['mailing', 'zip4'],
        'usps_type': ['mailing', 'uspstype'],
        'usps_bldgfirm': ['mailing', 'bldgfirm'],
        'election block_id': ['election', 'blockid'],
        'election precinct': ['election', 'precinct'],
    },

    'sources': [
        {
            'name':                 'opa_property',
            'table':                'opa_property',
            'db':                   'engine',
            'address_fields': {
                'street_address':       'street_address',
            },
            'tag_fields': [
                {
                    'key':              'opa_account_num',
                    'source_fields':     ['account_num'],
                },
                {
                    'key':              'opa_owner',
                    'source_fields':     ['owners'],
                },
                {
                    'key':              'opa_address',
                    'source_fields':     ['street_address'],
                },
            ],
        },
        {
            'name':                 'pwd_parcels',
            'table':                'pwd_parcel',
            'db':                   'engine',
            'address_fields': {
                'street_address':       'street_address',
            },
            'tag_fields': [
                {
                    'key':              'pwd_parcel_id',
                    'source_fields':     ['parcel_id'],
                },
            ],
        },
        {
            'name':                 'dor_parcels',
            'table':                'dor_parcel',
            'db':                   'engine',
            'address_fields': {
                'street_address':       'street_address',
            },
            'tag_fields': [
                {
                    'key':              'dor_parcel_id',
                    'source_fields':     ['parcel_id'],
                },
            ],
        },
        {
            'name':                 'dor_condos',
            'table':                'dor_condominium',
            'db':                   'engine',
            'address_fields': {
                'street_address':       'street_address',
            },
            'tag_fields': [
                {
                    'key':              'dor_parcel_id',
                    'source_fields':     ['parcel_id'],
                },
            ],
        },
        {
            'name':                 'info_commercial',
            'table':                'viewer_ais_sources.infogroup_commercial_2017_07',
            'db':                   'citygeo',
            'address_fields':       {
                'street_address':       'primary_address',
            },
            'tag_fields': [
                {
                    'key':              'info_company',
                    'source_fields':     ['company_name'],
                },
            ],
        },
        {
            'name':                 'info_residents',
            'table':                'viewer_ais_sources.infogroup_residential_2017_07',
            'db':                   'citygeo',
            'address_fields':       {
                'street_address':       'address',
            },
            'tag_fields': [
                {
                    'key':              'info_resident',
                    'source_fields':     ['contact_name'],
                },
            ],
        },
        {
            'name':                 'li_address_keys',
            'table':                'viewer_li.hansen_address',
            'db':                   'citygeo',
            'address_fields':       {
                'street_address':       'addr_concat',
            },
            'tag_fields': [
                {
                    'key':              'li_address_key',
                    'source_fields':     ['addrkey'],
                },
            ],
        },
        {
            'name':                 'li_eclipse_location_ids',
            'table':                'viewer_li.active_retired_parcels',
            'db':                   'citygeo',
            'address_fields':       {
                'base_address':       'base_address',
                'unit_num':           'unit_num',
                'unit_type':          'unit_type',
            },
            'preprocessor':         make_eclipse_address,
            'tag_fields': [
                {
                    'key':              'eclipse_location_id',
                    'source_fields':     ['addressobjectid'],
                },
            ],
        },
        {
            'name':                 'voters',
            'table':                'citygeo.latest_registered_voters',
            'db':                   'citygeo',
            'address_fields':       {
                'address_low':          'house__',
                'address_low_suffix':   'housenosuffix',
                'street_name':          'streetnamecomplete',
                'unit_num':             'apt__',
            },
            'preprocessor':         make_voter_address,
            'tag_fields': [
                {
                    'key':          'voter_name',
                    'source_fields': ["first_name", "middle_name", "last_name"],
                    'preprocessor': make_voter_name,
                },
            ],
        },
        {
            'name':                 'pwd_accounts',
            'table':                'gisuser.phl_gis_vw',
            'db':                   'pwd_billing',
            'address_fields':       {
                'street_address':       'address',
            },
            'preprocessor':         make_pwd_account_address,
            'tag_fields': [
                {
                    'key':          'pwd_account_num',
                    # 'source_field': 'water1_acc_no',
                    'source_fields': ['water1_acc_no'],
                },
            ],
        },
        {
            'name': 'zoning_documents',
            'table': 'viewer_citygeo.ais_zoning_documents',
            'db': 'citygeo',
            'address_fields': {
                'street_address': 'address',
            },
            'tag_fields': [
                {
                    'key': 'zoning_document_id',
                    # 'source_field': 'water1_acc_no',
                    'source_fields': ['doc_id'],
                },
            ],
        },
        {
            'name': 'building_footprints',
            'table': 'viewer_li.li_building_footprints',
            'db':    'citygeo',
            'address_fields': {
                'street_address': 'address',
            },
            'tag_fields': [
                {
                    'key': 'bin',
                    'source_fields': ['bin'],
                },
                {
                    'key': 'bin_parcel_id',
                    'source_fields': ['parcel_id_num'],
                },
            ],
        },
        {
            'name':                 'ng911_address_point',
            'table':                'ng911_address_point',
            'db':                   'engine',
            'address_fields': {
                'street_address':       'street_address',
            },
            'tag_fields': [
                {
                    'key':              'ng911_guid',
                    'source_fields':     ['guid'],
                },
                {
                    'key':              'ng911_address_point_placement',
                    'source_fields':     ['placement_type'],
                },
            ],
        },
        # {
        #     'name': 'rtt',
        #     'table': 'gis_dor_rttmapping.cris_properties',
        #     'db': 'gisp_t',
        #     'address_fields': {
        #         'address_low': 'house_number',
        #         'address_low_suffix': 'house_num_suffix',
        #         'address_high': 'house_num_range',
        #         'street_predir': 'street_dir',
        #         'street_postdir': 'street_dir_suffix',
        #         'street_name': 'street_name',
        #         'street_type': 'street_type',
        #         'unit_num': 'condo_unit',
        #     },
        #     'preprocessor': make_rtt_address,
        #     'tag_fields': [
        #         {
        #             'key': 'dor_parcel_id',
        #             'source_fields': ['reg_map_id'],
        #             'preprocessor': make_dor_parcel_id,
        #         },
        #     ],
        #     # Query only records with non-null reg_map_id
        #     'where':            'reg_map_id is not null',
        # },
    ]
}

# ERROR_TABLES = {
#     'dor_parcels': {
#         'error_table':      'dor_parcel_error',
#         'polygon_table':    'dor_parcel_error_polygon',
#     },
#     'addresses': {
#         'error_table':      'address_error',
#     },
# }

GEOCODE = {
    'centerline_offset':        5,
    'centerline_end_buffer':    17,
}

SERVICE_AREAS = {
    'layers': [
        # AIS_SOURCES
        {
            'layer_id':                     'center_city_district',
            'name':                         'Center City District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_ais_sources.centercitydistrict',
                    'value_field':          'district',
                },
            },
        },

        # DHS
        {
            'layer_id':                     'cua_zone',
            'name':                         'CUA Zone',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_dhs.cua_zones',
                    'value_field':          'cua_name',
                },
            },
        },

        # LNI
        {
            'layer_id':                     'li_district',
            'name':                         'L&I District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_li.li_districts',
                    'value_field':          'district',
                    'object_id_field':      'objectid',

                },
            },
        },

        # PHILLYRISING - TODO: decide whether to keep this, since it's unclear if program still exists.
        {
            'layer_id':                     'philly_rising_area',
            'name':                         'Philly Rising Area',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_citygeo.phillyrising_boundaries',
                    'value_field':          'site_name',
                    'object_id_field':      'objectid', # the field that was objectid_12 in oracle is now called just objectid in postgres.
                },
            },
        },

        # PLANNING
        {
            'layer_id':                     'census_tract_2010',
            'name':                         'Census Tract 2010',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.census_tracts_2010',
                    'value_field':          'tractce10',
                },
            },
        },
        {
            'layer_id':                     'census_block_group_2010',
            'name':                         'Census Block Group 2010',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.census_block_groups_2010',
                    'value_field':          'blkgrpce10',
                },
            },
        },
        {
            'layer_id':                     'census_block_2010',
            'name':                         'Census Block 2010',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.census_blocks_2010',
                    'value_field':          'blockce10',
                },
            },
        },
        {
            'layer_id':                     'census_tract_2020',
            'name':                         'Census Tract 2020',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.census_tracts_2020',
                    'value_field':          'tractce',
                },
            },
        },
        {
            'layer_id':                     'census_block_group_2020',
            'name':                         'Census Block Group 2020',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.census_block_groups_2020',
                    'value_field':          'blkgrpce',
                },
            },
        },
        {
            'layer_id':                     'census_block_2020',
            'name':                         'Census Block 2020',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.census_blocks_2020',
                    'value_field':          'blockce20',
                },
            },
        },
        {
            'layer_id':                     'council_district_2016',
            'name':                         'Council District 2016',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.council_districts_2016',
                    'value_field':          'district',
                },
            },
        },
        {
            'layer_id':                     'council_district_2024',
            'name':                         'Council District 2024',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.council_districts_2024',
                    'value_field':          'district',
                },
            },
        },       
        {
            'layer_id':                     'political_ward',
            'name':                         'Ward',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.political_wards',
                    'value_field':          'ward_num',
                },
            },
        },
        {
            'layer_id':                     'political_division',
            'name':                         'Ward Division',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.political_divisions',
                    'value_field':          'division_num',
                },
            },
        },
        {
            'layer_id':                     'state_house_rep_2012',
            'name':                         'State House Rep 2012',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.state_house_rep_2012',
                    'value_field':          'district_number',
                },
            },
        },
        {
            'layer_id':                     'state_house_rep_2022',
            'name':                         'State House Rep 2022',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.state_house_rep_2022',
                    'value_field':          'district',
                },
            },
        },
        {
            'layer_id':                     'state_senate_2012',
            'name':                         'State Senate 2012',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.state_senate_2012',
                    'value_field':          'district_number',
                },
            },
        },
        {
            'layer_id':                     'state_senate_2022',
            'name':                         'State Senate 2022',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.state_senate_2022',
                    'value_field':          'district',
                },
            },
        },
        {
            'layer_id':                     'us_congressional_2012',
            'name':                         'US Congressional 2012',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.us_congressional_2012',
                    'value_field':          'district_number',
                },
            },
        },
        {
            'layer_id':                     'us_congressional_2018',
            'name':                         'US Congressional 2018',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.us_congressional_2018',
                    'value_field':          'id',
                },
            },
        },
        {
            'layer_id':                     'us_congressional_2022',
            'name':                         'US Congressional 2022',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.us_congressional_2022',
                    'value_field':          'district',
                },
            },
        },
        {
            'layer_id':                     'planning_district',
            'name':                         'Planning District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.planning_districts',
                    'value_field':          'dist_name',
                    'object_id_field':      'objectid'
                },
            },
        },
        {
            'layer_id':                     'elementary_school',
            'name':                         'Elementary School',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.schooldist_catchments_es',
                    'value_field':          'es_name',
                },
            },
        },
        {
            'layer_id':                     'middle_school',
            'name':                         'Middle School',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.schooldist_catchments_ms',
                    'value_field':          'ms_name',
                },
            },
        },
        {
            'layer_id':                     'high_school',
            'name':                         'High School',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.schooldist_catchments_hs',
                    'value_field':          'hs_name',
                },
            },
        },
        # {
        #     'layer_id':             'neighborhood',
        #     'name':                 'Neighborhood',
        #     'description':          '',
        #     'sources': {
        #         'polygon':  {
        #             'db':                   'gis_sa',
        #             'table':                'gis_planning.Neighborhoods',
        #             'value_field':          'name',
        # #         },
        # #     },
        # # },
        {
            'layer_id':                     'zoning',
            'name':                         'Zoning',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.zoning_basedistricts',
                    'value_field':          'long_code',
                },
            },
        },
        # ZONING RCO OVERLAYS - CAN BE MULTIPLE PER ADDRESS? CLARIFY AND INCORPORATE
        {
            'layer_id':                     'zoning_rco',
            'name':                         'Zoning_RCO',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.zoning_rco',
                    'value_field':          'lni_id',
                },
            },
        },
        {
            'layer_id':                     'commercial_corridor',
            'name':                         'Commercial_Corridors',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.commercial_corridors',
                    'value_field':          'name',
                },
            },
        },
        {
            'layer_id':                     'historic_district',
            'name':                         'Historic Districts',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.historicdistricts_local',
                    'value_field':          'name',
                },
            },
        },
        {
            'layer_id':                     'historic_site',
            'name':                         'Historic Sites',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_planning.historic_sites_philreg',
                    'value_field':          'loc',
                    'method':               'yes_or_no'
                },
            },
            'value_method':                 'yes_or_no',
        },

        # STEEP SLOPE PROTECTION AREAS
        # {
        #     'layer_id':             'zoning_steepslopeprotectionarea',
        #     'name':                 'Zoning_SteepSlopeProtectionArea',
        #     'description':           '',
        #     'sources': {
        #         'polygon': {
        #             'db': '                 gis_sa',
        #             'table':                'gis_planning.Zoning_SteepSlopeProtectArea_r',
        #             'value_field':          'overlay_na',
        #         },
        #     },
        # },
        # FEMA FLOOD ZONES
        # {
        #     'layer_id':             'fema_flood_plain_100',
        #     'name':                 'Fema_Flood_Plain_100',
        #     'description':           '',
        #     'sources': {
        #         'polygon': {
        #             'db': '                 gis_sa',
        #             'table':                'gis_planning.FEMA_100_FLOOD_PLAIN',
        #             'value_field':          'fld_zone',
        #         },
        #     },
        # },
        # {
        #     'layer_id':             'fema_flood_plain_500',
        #     'name':                 'Fema_Flood_Plain_500',
        #     'description':           '',
        #     'sources': {
        #         'polygon': {
        #             'db': '                 gis_sa',
        #             'table':                'gis_planning.FEMA_500_FLOOD_PLAIN',
        #             'value_field':          'fld_zone',
        #         },
        #     },
        # },
        # # Land use was slowing the service area summary script down
        # # considerably.
        # # {
        # #   'layer_id':             'land_use',
        # #   'name':                 'Land Use',
        # #   'description':          '',
        # #   'sources': {
        # #       'polygon':  {
        # #           'db':                   'gis_sa',
        # #           'table':                'gis_planning.Land_Use',
        # #           'value_field':          'c_dig2desc',
        # #       },
        # #   },
        # # },
        # POLICE
        {
            'layer_id':                     'police_division',
            'name':                         'Police Division',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_police.boundaries_division',
                    'value_field':          'div_name',
                },
            },
        },
        # {
        #     'layer_id':             'police_sector',
        #     'name':                 'Police Sector',
        #     'description':          '',
        #     'sources': {
        #         'polygon':  {
        #             'db':                   'gis_sa',
        #             'table':                'gis_police.Boundaries_Sector',
        #             'value_field':          'distsec_id',
        #         },
        #     },
        # },
        {
            'layer_id':                     'police_district',
            'name':                         'Police District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_police.boundaries_district',
                    'value_field':          'dist_numc',
                    'transforms': [
                        'convert_to_integer',
                    ],
                },
            },
        },
        {
            'layer_id':                     'police_service_area',
            'name':                         'Police Service Area',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_police.boundaries_psa',
                    'value_field':          'psa_num',
                },
            },
        },
        # GIS_RDA
        #   SHOULD THIS GO IN SOURCES?
        #     investigate whether 2 addreses are same property
        # {
        #     'layer_id':             'rda_landbank_lama_assets',
        #     'name':                 'RDA_Landbank_Lama_Assets',
        #     'description':          '',
        #     'sources': {
        #         'polygon':  {
        #             'db':                   'gis_sa',
        #             'table':                'gis_rda.lama_assets_0725',
        #             'value_field':          'asset_id',
        #         },
        #     },
        # },

        # # GIS_RECYCLE
        # {
        #     'layer_id':             'recreation_district',
        #     'name':                 'Recreation District',
        #     'description':          '',
        #     'sources': {
        #         'polygon':  {
        #             'db':                   'gis_sa',
        #             'table':                'gis_orphan.Recreation_Districts',
        #             'value_field':          'dist_num',
        #         },
        #     },
        # },

       # STREETS
        {
            'layer_id':                     'rubbish_recycle_day',
            'name':                         'Rubbish/Recycle Day',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.rubbish_recyc_coll_bnd',
                    'value_field':          'collday',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.rubbish_recyc_coll_bnd_arcs',
                    'seg_id_field':         'seg_id',
                    'value_field':          'collday',
                },
            },
        },
        {
            'layer_id':                     'secondary_rubbish_day',
            'name':                         'Secondary Rubbish Day',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.rubbish_recyc_coll_bnd',
                    'value_field':          'secondary_rubbish_day',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.rubbish_recyc_coll_bnd_arcs',
                    'seg_id_field':         'seg_id',
                    'value_field':          'secondary_rubbish_day',
                },
            },
        },
        {
            'layer_id':                     'recycling_diversion_rate',
            'name':                         'Recycling Diversion Rate',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.recycling_diversion_rate',
                    'value_field':          'score',
                },
            },
        },
        {
            'layer_id':                     'leaf_collection_area',
            'name':                         'Leaf Collection Area',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.leaf_collection_areas',
                    'value_field':          'schedule',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.leaf_collection_areas_arc',
                    'seg_id_field':         'seg_id',
                    'value_field':          'schedule',
                },
            },
        },
        {
            'layer_id':                     'sanitation_area',
            'name':                         'Sanitation Area',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.sanitation_areas',
                    'value_field':          'sanarea',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.rubbish_recyc_coll_bnd_arcs',
                    'seg_id_field':         'seg_id',
                    'value_field':          'sanarea',
                },
            },
        },
        {
            'layer_id':                     'sanitation_district',
            'name':                         'Sanitation Districts',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.sanitation_districts',
                    'value_field':          'sandis',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.sanitation_districts_arc',
                    'seg_id_field':         'seg_id',
                    'value_field':          'sandis',
                },
            },
        },
        {
            'layer_id':                     'sanitation_convenience_center',
            'name':                         'Sanitation_Convenience_Center',
            'description':                  '',
            'sources': {
                'point': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.sanitation_convenience_centers',
                    'value_field':          'name',
                    'method':               'nearest',
                },
            },
        },
        {
            'layer_id':                     'clean_philly_block_captain',
            'name':                         'Clean_Philly_Block_Captains',
            'description':                  '',
            'sources': {
                'point': {
                    'db':                   'citygeo',
                    'table':                'citygeo.vw_cleanphl_block_captains',
                    'seg_id_field':         'seg_id',
                    'value_field':          'match_addr',
                    'method':               'seg_id',
                },
            },
            'value_method': 'yes_or_no',
        },
        {
            'layer_id':                     'historic_street',
            'name':                         'Historic Street',
            'description':                  '',
            'sources': {
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.historic_streets',
                    'seg_id_field':         'seg_id',
                    'value_field':          'on_street',
                    'object_id_field':      'objectid',
                },
            },
        },
        {
            'layer_id':                     'highway_district',
            'name':                         'Highway District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.highway_districts',
                    'value_field':          'district',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.highway_subsections_arc',
                    'seg_id_field':         'seg_id',
                    'value_field':          'district',
                },
            },
        },
        {
            'layer_id':                     'highway_section',
            'name':                         'Highway Section',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.highway_sections',
                    'value_field':          'distsect',
                    'transforms': [
                        'remove_whitespace',
                    ],
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.highway_subsections_arc',
                    'seg_id_field':         'seg_id',
                    'value_field':          'distsect',
                    'transforms': [
                        'remove_whitespace',
                    ],
                },
            },
        },
        {
            'layer_id':                     'highway_subsection',
            'name':                         'Highway Subsection',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.highway_subsections',
                    'value_field':          'distsectsub',
                    'transforms': [
                        'remove_whitespace',
                    ],
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.highway_subsections_arc',
                    'seg_id_field':         'seg_id',
                    'value_field':          'distsectsub',
                    'transforms': [
                        'remove_whitespace',
                    ],
                },
            },
        },
        {
            'layer_id':                     'traffic_district',
            'name':                         'Traffic District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.traffic_districts',
                    'value_field':          'district',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.traffic_districts_arc',
                    'seg_id_field':         'seg_id',
                    'value_field':          'district',
                },
            },
        },
        {
            'layer_id':                     'traffic_pm_district',
            'name':                         'Traffic PM District',
            'description':                  '',
            'sources': {
                # NOTE: these have m-values.
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.traf_pm_dist',
                    'value_field':          'pm_dist',
                },
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.traf_pm_dist_arc',
                    'seg_id_field':         'seg_id',
                    'value_field':          'pm_distric',
                },
            },
        },
        {
            'layer_id':                     'zip_code',
            'name':                         'ZIP Code',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.zipcodes_poly',
                    'value_field':          'code',
                },
                'line_dual': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.zipcodes_arc',
                    'seg_id_field':         'seg_id',
                    'left_value_field':     'zip_left',
                    'right_value_field':    'zip_right',
                },
            },
        },
        {
            'layer_id':                     'street_light_route',
            'name':                         'Street Light Route',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.street_light_routes',
                    'value_field':          'route',
                },
            },
        },
        {
            'layer_id':                     'lane_closure',
            'name':                         'Lane Closure',
            'description': '',
            'sources': {
                'line_single': {
                    'db':                   'citygeo',
                    'table':                'viewer_streets.laneclosure_master',
                    'seg_id_field':         'seg_id',
                    'value_field':          'permitnumber',
                    'object_id_field':      'objectid',
                },
            },
        },

        # PWD
        {
            'layer_id':                     'pwd_maint_district',
            'name':                         'PWD Maintenance District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_pwd.maint_dist',
                    'value_field':          'cs_distric',
                },
            },
        },
        {
            'layer_id':                     'pwd_pressure_district',
            'name':                         'PWD Pressure District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_pwd.pres_dist',
                    'value_field':          'acronym',
                },
            },
        },
        {
            'layer_id':                     'pwd_treatment_plant',
            'name':                         'PWD Treatment Plant',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_pwd.wtpsa',
                    'value_field':          'acronym',
                    'object_id_field':      'objectid'
                },
            },
        },
        {
            'layer_id':                     'pwd_water_plate',
            'name':                         'PWD Water Plate',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_pwd.water_plate_index',
                    'value_field':          'water_plate',
                },
            },
            # 'source_account':       'gis',
        },
        {
            'layer_id':                     'pwd_center_city_district',
            'name':                         'PWD Center City District',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_pwd.center_city_district',
                    'value_field':          'district',
                },
            },
        },
        # PWD_WATERSHEDS
        {
            'layer_id':                     'major_phila_watershed',
            'name':                         'Major Watersheds Phila',
            'description':                  '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_pwd_watersheds.major_watersheds_phila',
                    'value_field':          'watershed_name',
                },
            },
        },
        # GIS_GSG
        # {
        #     'layer_id':                     'litter_schema_test',
        #     'name':                         'Litter Schema Test',
        #     'description':                  '',
        #     'sources': {
        #         'polygon':  {
        #             'db':                   'gis_sa',
        #             'table':                'gis_gsg.LITTER_SCHEMA_TEST',
        #             'value_field':          'score',
        #         },
        #     },
        # },
        # OHCD
        {
            'layer_id':                     'neighborhood_advisory_committee',
            'name':                         'Neighborhood Advisory Committees',
            'description': '',
            'sources': {
                'polygon': {
                    'db': 'citygeo',
                    'table':                'viewer_planning.neighborhoodadvisorycommittees',
                    'value_field':          'organization',
                },
            },
        },
        # PPR
        {
            'layer_id':                     'ppr_friends',
            'name':                         'PPR Friends',
            'description': '',
            'sources': {
                'point': {
                    'db':                   'citygeo',
                    'table':                'viewer_ppr.ppr_friends_groups',
                    'value_field':          'friends_group_name',
                    'method':               'nearest',
                },
            },
        },
        # FIRE
        {
            'layer_id':                     'engine_local',
            'name':                         'Engine Local',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_fire.engine_local',
                    'value_field':          'engine_num',
                },
            },
        },
        {
            'layer_id':                     'ladder_local',
            'name':                         'Ladder Local',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_fire.ladder_local',
                    'value_field':          'ladder_num',
                },
            },
        },
        # HEALTH
        {
            'layer_id':                     'tobacco_retailer_permit_capped',
            'name':                         'Tobacco Retailer Density Caps',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_health.tobretailerdensitycaps',
                    'value_field':          'capped',
                },
            },
        },
        {
            'layer_id':                     'tobacco_free_school_zones',
            'name':                         'Tobacco Free School Zones',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_health.tobfreeschoolparcelbuffermerge',
                    'value_field':          'objectid',
                    'method':               'yes_or_no'
                },
            },
            'value_method':                 'yes_or_no',

        },
        # H3 HEX GRIDS
        {
            'layer_id':                     'h3_hex_grid_r7',
            'name':                         'H3 Hex Grid R7',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_citygeo.h3_hex_grid_r7',
                    'value_field':          'grid_id',
                },
            },
        },
        {
            'layer_id':                     'h3_hex_grid_r8',
            'name':                         'H3 Hex Grid R8',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_citygeo.h3_hex_grid_r8',
                    'value_field':          'grid_id',
                },
            },
        },
        {
            'layer_id':                     'h3_hex_grid_r9',
            'name':                         'H3 Hex Grid R9',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_citygeo.h3_hex_grid_r9',
                    'value_field':          'grid_id',
                },
            },
        },
        {
            'layer_id':                     'h3_hex_grid_r10',
            'name':                         'H3 Hex Grid R10',
            'description': '',
            'sources': {
                'polygon': {
                    'db':                   'citygeo',
                    'table':                'viewer_citygeo.h3_hex_grid_r10',
                    'value_field':          'grid_id',
                },
            },
        },
    ],
}

ADDRESS_SUMMARY = {
    # Order in which to look for geocode XYs
    'geocode_types': [
        'pwd_parcel',
        'dor_parcel',
        'ng911',
        'true_range',
    ],
    # 'geocode_types_on_curb': [
    #     'pwd_curb',
    #     'dor_curb',
    # ],
    'geocode_types_in_street': [
        'pwd_street',
        'dor_street',
        'true_range',
    ],
    'geocode_priority': {
        'dor_curb': 9,
        'pwd_curb': 8,
        'true_range': 6,
        'dor_street': 5,
        'pwd_street': 4,
        'pwd_parcel': 1,
        'dor_parcel': 2,
        'centerline': 7,
        'pwd_parcel_spatial': 10,
        'dor_parcel_spatial': 11,
        'pwd_parcel_front': 12,
        'dor_parcel_front': 13,
        'ng911': 3,
        'unable_to_geocode': 99
    },

    # Max number of attribute values to pipe-delimit
    'max_values':           5,
    # TODO: strip out relationship fields from tag fields
    'tag_fields': [
        # traverse_links was deprecated in favor of dedicated relationship
        # tables: address-parcel, address-street, and address-property
        {
            'name':                 'zip_code',
            'tag_key':              'usps_zipcode',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'zip_4',
            'tag_key':              'usps_zip4',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'usps_type',
            'tag_key':              'usps_type',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'usps_bldgfirm',
            'tag_key':              'usps_bldgfirm',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'election_block_id',
            'tag_key':              'election block_id',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'election_precinct',
            'tag_key':              'election precinct',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'seg_id',
            'tag_key':              'seg_id',
            'type':                 'number',
            'traverse_links':       'true',
        },
        {
            'name':                 'seg_side',
            'tag_key':              'seg_side',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'pwd_parcel_id',
            'tag_key':              'pwd_parcel_id',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'dor_parcel_id',
            'tag_key':              'dor_parcel_id',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'opa_account_num',
            'tag_key':              'opa_account_num',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'opa_owners',
            'tag_key':              'opa_owner',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'opa_address',
            'tag_key':              'opa_address',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'pwd_account_nums',
            'tag_key':              'pwd_account_num',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'li_address_key',
            'tag_key':              'li_address_key',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'voters',
            'tag_key':              'voter_name',
            'type':                 'text',
            'traverse_links':       'false',
        },
        {
            'name':                 'info_residents',
            'tag_key':              'info_resident',
            'type':                 'text',
            'traverse_links':       'false',
        },
        {
            'name':                 'info_companies',
            'tag_key':              'info_company',
            'type':                 'text',
            'traverse_links':       'false',
        },
        {
            'name':                 'eclipse_location_id',
            'tag_key':              'eclipse_location_id',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'zoning_document_ids',
            'tag_key':              'zoning_document_id',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'bin',
            'tag_key':              'bin',
            'type':                 'text',
            'traverse_links':       'true',
        },
        {
            'name':                 'bin_parcel_id',
            'tag_key':              'bin_parcel_id',
            'type':                 'text',
            'traverse_links':       'false',
        },
    ],
    'non_summary_tags': ['bin_parcel_id', 'info_resident', 'info_company', 'voter_name', 'ng911_guid', 'ng911_address_point_placement'],
}

SWAGGER = {
    "swagger_version": "2.0",
    "title": "AIS",
    #"basePath": 'api.phila.gov/ais/v1',
    "specs_route": "/specs",
    "specs": [
        {
            "version": "1.0",
            "title": "AIS API v1",
            "endpoint": 'spec',
            "description": 'Address Information System API Version 1.0',
            "route": '/spec'
            # # for versions, use rule_filter to assign endpoints to versions
            # rule_filter is optional
            # it is a callable to filter the views to extract
            # "rule_filter": lambda rule: rule.endpoint.startswith(
            #     'should_be_v1_only'
            # )
        }
    ],
    "static_url_path": "",
}
