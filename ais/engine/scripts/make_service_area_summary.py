from datetime import datetime
from datetime import datetime
from copy import deepcopy
import datum
from ais import app

# DEV
import traceback
from pprint import pprint

def main():

    print('Starting...')
    start = datetime.now()

    """
    TODO
    - This might perform better if we do one big spatial join at the beginning
      between address summary and service area polygons.
    """

    """SET UP"""
    config = app.config
    db = datum.connect(config['DATABASES']['engine'])
    sa_layer_defs = config['SERVICE_AREAS']['layers']
    sa_layer_ids = [x['layer_id'] for x in sa_layer_defs]
    poly_table = db['service_area_polygon']
    line_single_table = db['service_area_line_single']
    line_dual_table = db['service_area_line_dual']
    point_table = db['service_area_point']
    #sa_summary_table = db['service_area_summary']
    address_summary_table = db['address_summary']
    address_summary_fields = [
        'street_address',
        'geocode_x',
        'geocode_y',
        # 'seg_id',
        # 'seg_side',
    ]
    sa_summary_fields = [{'name': 'street_address', 'type': 'text'}]
    sa_summary_fields += [{'name': x, 'type': 'text'} for x in sa_layer_ids]
    sa_summary_row_template = {x: '' for x in sa_layer_ids}

    # DEV
    WRITE_OUT = True

    # Keep poly rows in memory so we make less trips to the database for overlapping
    # points.
    # xy_map = {}  # x => y => [sa_poly_rows]

    """MAIN"""
    #
    if WRITE_OUT:
        print('Dropping service area summary table...')
        db.drop_table('service_area_summary')

        print('Creating service area summary table...')
        db.create_table('service_area_summary', sa_summary_fields)

    sa_summary_table = db['service_area_summary']

    # print('Reading single-value service area lines...')
    # line_single_map = {}  # layer_id => seg_id => value
    # line_singles = ais_db.read(line_single_table, ['*'])

    # for line_single in line_singles:
    # 	layer_id = line_single['layer_id']
    # 	seg_id = line_single['seg_id']
    # 	value = line_single['value']
    # 	if layer_id not in line_single_map:
    # 		line_single_map[layer_id] = {}
    # 	line_single_map[layer_id][seg_id] = value

    # print('Reading dual-value service area lines...')
    # line_dual_map = {}  # layer_id => seg_id => value
    # line_duals = ais_db.read(line_dual_table, ['*'])

    # for line_dual in line_duals:
    # 	layer_id = line_dual['layer_id']
    # 	seg_id = line_dual['seg_id']
    # 	left_value = line_dual['left_value']
    # 	right_value = line_dual['right_value']
    # 	if layer_id not in line_dual_map:
    # 		line_dual_map[layer_id] = {}

    # 	line_dual_map[layer_id][seg_id] = {}
    # 	line_dual_map[layer_id][seg_id]['left'] = left_value
    # 	line_dual_map[layer_id][seg_id]['right'] = right_value

    print('Reading address summary...')
    address_summary_rows = address_summary_table.read(\
        fields=address_summary_fields, \
        sort=['geocode_x', 'geocode_y']\
    )

    sa_summary_rows = []

    # Sort address summary rows by X, Y and use these to compare the last row
    # to the current one. This minimizes trips to the database for poly values.
    last_x = None
    last_y = None
    last_sa_rows = None
    #
    print('Intersecting addresses and service area polygons...')
    for i, address_summary_row in enumerate(address_summary_rows):
        try:
            if i % 10000 == 0:
                print(i)

                # Write in chunks
                if WRITE_OUT: #and i % 50000 == 0:
                    sa_summary_table.write(sa_summary_rows)
                    sa_summary_rows = []

            # Get attributes
            street_address = address_summary_row['street_address']
            # seg_id = address_summary_row['seg_id']
            # seg_side = address_summary_row['seg_side']
            x = address_summary_row['geocode_x']
            y = address_summary_row['geocode_y']

            sa_rows = None
            # if x in xy_map:
            # 	y_map = xy_map[x]
            # 	if y in y_map:
            # 		sa_rows = y_map[y]
            if last_x and (last_x == x and last_y == y):
                sa_rows = last_sa_rows

            if sa_rows is None and None not in (x,y):
                # Get intersecting service areas
                where = f'ST_Intersects(geom, ST_SetSrid(ST_Point({x}, {y}), 2272))'
                sa_rows = poly_table.read(fields=['layer_id', 'value'], where=where, return_geom=False)

                # Add to map
                # x_map = xy_map[x] = {}
                # x_map[y] = sa_rows

            # Create and insert summary row
            sa_summary_row = deepcopy(sa_summary_row_template)
            sa_summary_row['street_address'] = street_address
            if sa_rows: 
                update_dict = {}
                for x in sa_rows: 
                    if update_dict.get(x['layer_id']) == None: 
                        update_dict[x['layer_id']] = []
                    update_dict[x['layer_id']].append(x['value'])
                for layer_id, _ in update_dict.items(): 
                    update_dict[layer_id].sort()
                    update_dict[layer_id] = '|'.join(update_dict[layer_id])
                sa_summary_row.update(update_dict)

            sa_summary_rows.append(sa_summary_row)

            last_x = x
            last_y = y
            last_sa_rows = sa_rows

        except Exception as e:
            print(traceback.format_exc())
            raise e

    # Clear out XY map
    # xy_map = {}

    if WRITE_OUT:
        print('Writing service area summary rows...')
        sa_summary_table.write(sa_summary_rows)
        del sa_summary_rows

    # # Update where method = yes_or_no:
    # for sa_layer_def in sa_layer_defs:
    # 	layer_id = sa_layer_def['layer_id']
    # 	if 'polygon' in sa_layer_def['sources']:
    # 		method = sa_layer_def['sources']['polygon'].get('method')
    # 		if method == 'yes_or_no':
    # 			stmt = f'''
    # 					UPDATE service_area_summary sas
    # 					SET {layer_id} = (
    # 					CASE
    # 					WHEN {layer_id} != '' THEN 'yes'
    # 					ELSE 'no'
    # 					END);
    # 					'''
    # 			db.execute(stmt)
    # 			# print(ais_db.c.rowcount)
    # 			db.save()
    ################################################################################
    # SERVICE AREA LINES
    ################################################################################

    if WRITE_OUT:
        print('\n** SERVICE AREA LINES ***\n')
        print('Creating indexes...')
        sa_summary_table.create_index('street_address')

        print('Creating temporary indexes...')
        address_summary_table.create_index('seg_id')

        for sa_layer_def in sa_layer_defs:
            layer_id = sa_layer_def['layer_id']

            if 'line_single' in sa_layer_def['sources']:
                print(f'Updating from {layer_id}...')
                stmt = f'''
                    UPDATE service_area_summary sas
                    SET {layer_id} = sals.value
                    FROM address_summary ads, service_area_line_single sals
                    WHERE
                        sas.street_address = ads.street_address AND
                        sals.seg_id = ads.seg_id AND
                        sals.layer_id = '{layer_id}' AND
                        sals.value <> ''
                '''
                db.execute(stmt)
                # print(ais_db.c.rowcount)
                db.save()

            elif 'line_dual' in sa_layer_def['sources']:
                print(f'Updating from {layer_id}...')
                stmt = f'''
                    UPDATE service_area_summary sas
                    SET {layer_id} = CASE WHEN (ads.seg_side = 'L') THEN sald.left_value ELSE sald.right_value END
                    FROM address_summary ads, service_area_line_dual sald
                    WHERE sas.street_address = ads.street_address AND
                        sald.seg_id = ads.seg_id AND
                        sald.layer_id = '{layer_id}' AND
                        CASE WHEN (ads.seg_side = 'L') THEN sald.left_value ELSE sald.right_value END <> ''
                '''
                db.execute(stmt)
                # print(ais_db.c.rowcount)
                db.save()

        print('Dropping temporary index...')
        address_summary_table.drop_index('seg_id')

    #############################################################################
    # SERVICE AREA POINTS
    #############################################################################
    if WRITE_OUT:
        print('Finding nearest service area point to each address...')
        for sa_layer_def in sa_layer_defs:
            layer_id = sa_layer_def['layer_id']
            if 'point' in sa_layer_def['sources']:
                method = sa_layer_def['sources']['point'].get('method')
                if method == 'nearest':
                    print(f'Updating from {layer_id}...')
                    stmt = f'''
                            with sap_layer as
                            (
                                select sap.*
                                from service_area_point sap
                                where sap.layer_id = '{layer_id}'
                            )
                            update service_area_summary sas
                            set {layer_id} = sapf.value
                            from
                                (
                                select ads.street_address, saplv.value
                                from address_summary ads
                                cross join lateral
                                (
                                    select sap_layer.value
                                    from sap_layer
                                    order by st_setsrid(st_point(ads.geocode_x, ads.geocode_y), 2272) <-> sap_layer.geom limit 1
                                ) as saplv
                                ) sapf
                            where sas.street_address = sapf.street_address
                        '''
                    db.execute(stmt)
                    db.save()

                elif method == 'seg_id':
                    print(f'Updating from {layer_id}...')
                    stmt = f'''
                            UPDATE service_area_summary sas
                            SET {layer_id} = sap.value
                            FROM address_summary ads, service_area_point sap
                            WHERE
                                sas.street_address = ads.street_address AND
                                sap.seg_id = ads.seg_id AND
                                sap.layer_id = '{layer_id}' AND
                                sap.value <> ''
                        '''
                    db.execute(stmt)
                    db.save()

    #################
    # NEAREST POLY	#
    #################
    if WRITE_OUT:
        print('Finding nearest service area polygon to each address...')
        for sa_layer_def in sa_layer_defs:
            layer_id = sa_layer_def['layer_id']
            if 'polygon' in sa_layer_def['sources']:
                method = sa_layer_def['sources']['polygon'].get('method')
                if method != 'nearest_poly':
                    continue
                print(f'Updating from {layer_id}...')
                stmt = f'''
                        with sap_layer as
                        (
                            select sap.*
                            from service_area_polygon sap
                            where sap.layer_id = '{layer_id}'
                        )
                        update service_area_summary sas
                        set {layer_id} = sapf.value
                        from
                            (
                            select ads.street_address, saplv.value
                            from address_summary ads
                            cross join lateral
                            (
                                select sap_layer.value
                                from sap_layer
                                order by st_setsrid(st_point(ads.geocode_x, ads.geocode_y), 2272) <-> sap_layer.geom limit 1
                            ) as saplv
                            ) sapf
                        where sas.street_address = sapf.street_address
                    '''
                db.execute(stmt)
                db.save()
    ################################
    # Update where method = yes_or_no:
    print("Updating service_area_summary values where method = 'yes_or_no'")
    for sa_layer_def in sa_layer_defs:
        layer_id = sa_layer_def['layer_id']
        method = sa_layer_def.get('value_method')
        if method == 'yes_or_no':
            stmt = f'''
                    UPDATE service_area_summary sas
                    SET {layer_id} = (
                    CASE
                    WHEN {layer_id} != '' THEN 'Yes'
                    ELSE 'No'
                    END);
                    '''
            db.execute(stmt)
            db.save()
    #################################
    # TODO Update address summary zip_code with point-in-poly value where USPS seg-based is Null (parameterize field to update, set in config, and execute in for loop)
    print("Updating null address_summary zip_codes from service_areas...")
    stmt = '''
    DROP INDEX public.address_summary_opa_owners_trigram_idx;
    DROP INDEX public.address_summary_sort_idx;
    DROP INDEX public.address_summary_street_address_idx;
    DROP INDEX public.ix_address_summary_dor_parcel_id;
    DROP INDEX public.ix_address_summary_opa_account_num;
    DROP INDEX public.ix_address_summary_pwd_parcel_id;
    DROP INDEX public.ix_address_summary_seg_id;

    UPDATE address_summary asum
    SET zip_code = sas.zip_code
    from service_area_summary sas
    where sas.street_address = asum.street_address and (asum.zip_code is Null or asum.zip_code in ('', null));

    CREATE INDEX ix_address_summary_seg_id
        ON public.address_summary USING btree
        (seg_id);
        
    CREATE INDEX address_summary_opa_owners_trigram_idx
        ON public.address_summary USING gin
        (opa_owners gin_trgm_ops);

    CREATE INDEX address_summary_sort_idx
        ON public.address_summary USING btree
        (street_name, street_suffix, street_predir, street_postdir, address_low, address_high, unit_num);
        
    CREATE INDEX address_summary_street_address_idx
        ON public.address_summary USING btree
        (street_address);

    CREATE INDEX ix_address_summary_dor_parcel_id
        ON public.address_summary USING btree
        (dor_parcel_id);

    CREATE INDEX ix_address_summary_opa_account_num
        ON public.address_summary USING btree
        (opa_account_num);

    CREATE INDEX ix_address_summary_pwd_parcel_id
        ON public.address_summary USING btree
        (pwd_parcel_id);
    '''
    db.execute(stmt)
    db.save()
    #################################
    # Clean up:
    db.close()

    print(f'Finished in {datetime.now() - start}')
