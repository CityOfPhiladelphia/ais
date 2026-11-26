"""Service area layer definitions used by the engine build and API."""

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
        # PPR
        {
            'layer_id':                     'ppr_ops_district',
            'name':                         'PPR Ops districts',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_ppr.ppr_ops_districts',
                    'value_field':          'ppr_ops_district',
                    'object_id_field':      'objectid',

                },
            },
        },
        {
            'layer_id':                     'ppr_streettree_district',
            'name':                         'PPR Street Tree districts',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_ppr.ppr_streettree_districts',
                    'value_field':          'ppr_st_tree_district',
                    'object_id_field':      'objectid',

                },
            },
        },
        {
            'layer_id':                     'ppr_parktree_district',
            'name':                         'PPR Park Tree districts',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_ppr.ppr_parktree_districts',
                    'value_field':          'ppr_pk_tree_district_id',
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
                    'table':                'viewer_cco.political_wards',
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
                    'table':                'viewer_cco.political_divisions',
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
        {
            'layer_id':                     'police_abandoned_vehicle_police_district_grid',
            'name':                         'Police Abandoned Vehicle Police District Grid',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_police.abandoned_vehicle_police_district_grids',
                    'value_field':          'grid_id',
                },
            },
        },
        {
            'layer_id':                     'police_abandoned_vehicle_sanitation_grid',
            'name':                         'Police Abandoned Vehicle Sanitation Grid',
            'description':                  '',
            'sources': {
                'polygon':  {
                    'db':                   'citygeo',
                    'table':                'viewer_police.abandoned_vehicle_sanitation_grids',
                    'value_field':          'grid_id',
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
                    'value_field':          'first_in_engine',
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
