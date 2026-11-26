"""Data source definitions, address preprocessors, and summary schema."""

import re

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
    'opa_account_num_changes': {
        'db':               'citygeo',
        'table':            'viewer_opa.pin_account_number_change_map',
        'field_map': {
            'pin':                       'pin',
            'old_opa_account_num':       'old_opa_account_num',
            'new_opa_account_num':       'new_opa_account_num',
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
    if not a:
        return None
    a = re.sub(r'-R(EAR)?(?= )', 'R', a)
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

def make_legacy_certificate_of_occupancy_permit_address(comps):
    out_comps = (comps['address_low'], comps['street_predir'], comps['street_name'], comps['street_suffix'])
    out_comps = [x for x in out_comps if x and len(multi_strip(x)) > 0]
    return ' '.join(out_comps)

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
            'table':                'viewer_li.eclipse_address',
            'db':                   'citygeo',
            'address_fields':       {
                'base_address':       'base_address',
                'unit_num':           'unit_number',
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
            'table':                'viewer_pwd.accounts',
            'db':                   'citygeo',
            'address_fields':       {
                'street_address':       'one_address',
            },
            'preprocessor':         make_pwd_account_address,
            'tag_fields': [
                {
                    'key':          'pwd_account_num',
                    'source_fields': ['water_account'],
                },
            ],
            'where':                'one_address IS NOT NULL AND water_account IS NOT NULL',
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
            'name': 'legacy_certificate_of_occupancy_permits',
            'table': 'viewer_citygeo.imaging_archive_deptli_cos',
            'db': 'citygeo',
            'address_fields': {
                'address_low': 'st_no',
                'street_predir': 'st_dir',
                'street_name': 'st_name',
                'street_suffix': 'st_suffix'
            },
            'preprocessor':         make_legacy_certificate_of_occupancy_permit_address,
            'tag_fields': [
                {
                    'key': 'legacy_certificate_of_occupancy_permit_nums',
                    'source_fields': ['permit_num'],
                },
            ],
        },
        {
            'name': 'legacy_certificate_of_use_and_occupancy_permits',
            'table': 'viewer_citygeo.imaging_archive_deptli_permit_tracking_cos',
            'db': 'citygeo',
            'address_fields': {
                'address_low': 'st_no',
                'street_predir': 'st_dir',
                'street_name': 'st_name',
                'street_suffix': 'st_suffix'
            },
            'preprocessor':         make_legacy_certificate_of_occupancy_permit_address,
            'tag_fields': [
                {
                    'key': 'legacy_certificate_of_use_and_occupancy_permit_nums',
                    'source_fields': ['permit_num'],
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
        {
            'name':                 'legacy_certificate_of_occupancy_permit_nums',
            'tag_key':              'legacy_certificate_of_occupancy_permit_nums',
            'type':                 'text',
            'traverse_links':       'false',
        },
        {
            'name':                 'legacy_certificate_of_use_and_occupancy_permit_nums',
            'tag_key':              'legacy_certificate_of_use_and_occupancy_permit_nums',
            'type':                 'text',
            'traverse_links':       'false',
        },
    ],
    'non_summary_and_api_tags': ['bin_parcel_id', 'info_resident', 'info_company', 'voter_name', 'ng911_guid', 'ng911_address_point_placement'],
    'non_summary_tags': ['bin_parcel_id', 'info_resident', 'info_company', 'voter_name', 'ng911_guid', 'ng911_address_point_placement', 'legacy_certificate_of_occupancy_permit_nums', 'legacy_certificate_of_use_and_occupancy_permit_nums']
}
