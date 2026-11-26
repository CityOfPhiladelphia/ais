import sys
from datetime import datetime
from shapely.wkt import loads
from ais import app
from ais.engine.db import connect

"""
TRANSFORMS

Define functions here that can be referenced in ais/config/service_areas.py for mutating
service area rows. Eventually, these could probably go in their own file
and be used by any script that iterates over rows dictionaries.

Args: row, value_field
Return: row
"""

def convert_to_integer(row, value_field):
    value = row[value_field]
    int_value = int(value)
    row[value_field] = int_value
    return row

def remove_whitespace(row, value_field):
    value = row[value_field]
    no_whitespace = value.replace(' ', '')
    row[value_field] = no_whitespace
    return row

def main():
    start = datetime.now()
    print('Starting...')

    """SET UP"""

    config = app.config
    db = connect(config['DATABASES']['engine'])
    poly_table = db['service_area_polygon']
    line_single_table = db['service_area_line_single']
    line_dual_table = db['service_area_line_dual']
    point_table = db['service_area_point']
    layer_table = db['service_area_layer']
    layers = config['SERVICE_AREAS']['layers']
    geom_field = 'shape'
    # sde_srid = 2272
    WRITE_OUT = True

    print('\n** SERVICE AREA LAYERS **')

    if WRITE_OUT:
        print('Deleting existing service area layers...')
        layer_table.delete()

        print('Writing service area layers...')
        keys = ['layer_id', 'name', 'description']
        layer_rows = [{key: layer[key] for key in keys} for layer in layers]
        db['service_area_layer'].write(layer_rows)

    print('\n** SERVICE AREAS **')

    if WRITE_OUT:
        print('Dropping indexes...')
        line_single_table.drop_index('seg_id')
        line_dual_table.drop_index('seg_id')

        print('Deleting existing service area polys...')
        poly_table.delete()
        print('Deleting existing service area single-value lines...')
        line_single_table.delete()
        print('Deleting existing service area dual-value lines...')
        line_dual_table.delete()
        print('Deleting existing service area points...')
        point_table.delete()

    polys = []
    line_singles = []
    line_duals = []
    points = []
    empty_geometry_fail = False

    print('Reading service areas...')
    source_dbs = {}

    for layer in layers:
        layer_id = layer['layer_id']
        print('  - {}'.format(layer_id))
        sources = layer['sources']

        # Check for conflicting source types
        if 'line_single' in sources and 'line_dual' in sources:
            raise Exception('Too many line sources for {}'.format(layer_id))

        for source_type, source in sources.items():
            # Reuse cached connection per DB
            source_db_name = source['db']
            if source_db_name not in source_dbs:
                try:
                    source_dbs[source_db_name] = connect(config['DATABASES'][source_db_name])
                except KeyError:
                    print('Database {} not found'.format(layer_id))
                    continue
            source_db = source_dbs[source_db_name]

            source_table_name = source['table']
            source_table = source_db[source_table_name]
            source_geom_field = source_table.geom_field
            # If no object ID field is specified, default to `objectid`.
            object_id_field = source.get('object_id_field', 'objectid')
            
            # If there are transforms, reference their functions
            transforms = source.get('transforms', [])
            transform_map = {}
            for transform in transforms:
                f = getattr(sys.modules[__name__], transform)
                transform_map[transform] = f
            
            # POLYGON
            if source_type == 'polygon':
                value_field = source['value_field']
                source_fields = [value_field, object_id_field]
                source_rows = source_table.read(fields=source_fields, 
                                                geom_field=geom_field)

                for i, source_row in enumerate(source_rows):
                    # Transform if necessary
                    for f in transform_map.values():
                        source_row = f(source_row, value_field)
                    
                    value = source_row[value_field]

                    # Remove excess whitespace from strings. This isn't a transform
                    # because we want to do it to all strings.
                    if isinstance(value, str):
                        value = value.strip()

                    # Alert on null geometries 
 
                    if not source_row[source_geom_field]:
                        print(f'Empty geometry found in {source_db_name}.{source_table_name}!')
                        print(f'Source row: {source_row}')
                        empty_geometry_fail = True
                    
                    poly = {
                        'layer_id': 			layer_id,
                        'source_object_id': 	source_row[object_id_field],
                        'value': 				value or '',
                        'geom': 				source_row[source_geom_field],
                    }
                    polys.append(poly)


            # LINE SINGLE
            if source_type == 'line_single':
                value_field = source['value_field']
                seg_id_field = source['seg_id_field']
                source_fields = [value_field, object_id_field, seg_id_field]
                source_rows = source_table.read(fields=source_fields)

                for i, source_row in enumerate(source_rows):
                    # Transform if necessary
                    for f in transform_map.values():
                        source_row = f(source_row, value_field)

                    value = source_row[value_field]

                    # Remove excess whitespace from strings. This isn't a transform
                    # because we want to do it to all strings.
                    if isinstance(value, str):
                        value = value.strip()

                    line_single = {
                        'layer_id': 			layer_id,
                        'source_object_id': 	source_row[object_id_field],
                        'seg_id':				source_row[seg_id_field],
                        'value': 				value or '',
                    }
                    line_singles.append(line_single)

            # LINE DUAL
            if source_type == 'line_dual':
                left_value_field = source['left_value_field']
                right_value_field = source['right_value_field']
                seg_id_field = source['seg_id_field']
                source_fields = [
                    left_value_field,
                    right_value_field,
                    object_id_field,
                    seg_id_field
                ]
                source_rows = source_table.read(fields=source_fields)

                for i, source_row in enumerate(source_rows):
                    # Transform if necessary
                    for f in transform_map.values():
                        source_row = f(source_row, value_field)

                    left_value = source_row[left_value_field]
                    right_value = source_row[right_value_field]

                    line_dual = {
                        'layer_id': 			layer_id,
                        'source_object_id': 	source_row[object_id_field],
                        'seg_id':				source_row[seg_id_field],
                        'left_value': 			left_value or '',
                        'right_value': 			right_value or '',
                    }
                    line_duals.append(line_dual)


            # POINT
            if source_type == 'point':
                value_field = source['value_field']
                seg_id_field = source.get('seg_id_field', '')
                method = source.get('method', '')
                source_fields = [value_field, object_id_field] if method != 'seg_id' else [value_field]
                if seg_id_field:
                    source_fields.append(seg_id_field)
                source_rows = source_table.read(fields=source_fields, \
                                                geom_field=geom_field) if method != 'seg_id' else source_table.read(fields=source_fields)

                for i, source_row in enumerate(source_rows):
                    # Transform if necessary
                    for f in transform_map.values():
                        source_row = f(source_row, value_field)

                    value = source_row[value_field]

                    # Remove excess whitespace from strings. This isn't a transform
                    # because we want to do it to all strings.
                    if isinstance(value, str):
                        value = value.strip()

                    point = {
                        'layer_id': layer_id,
                        'source_object_id': source_row[object_id_field] if method != 'seg_id' else None,
                        'seg_id': source_row[seg_id_field] if seg_id_field else None,
                        'value': value or '',
                        'geom': source_row[source_geom_field] if method != 'seg_id' else loads('POINT(0 0)').wkt,
                    }
                    points.append(point)
    if empty_geometry_fail:
        raise AssertionError('Encountered earlier empty geometry, that shouldnt happen!! Full row will be logged in earlier logs for this engine build script. Failing out..')


    if WRITE_OUT:
        print(f'Writing {len(polys)} service area polygons...')
        poly_table.write(polys, chunk_size=50000)

        print(f'Writing {len(line_singles)} service area single-value lines...')
        line_single_table.write(line_singles, chunk_size=50000)

        print(f'Writing {len(line_duals)} service area line dual-value lines...')
        line_dual_table.write(line_duals, chunk_size=50000)

        print(f'Writing {len(points)} service area points...')
        point_table.write(points, chunk_size=50000)

        print('Creating indexes...')
        line_single_table.create_index('seg_id')
        line_dual_table.create_index('seg_id')

    for sdb in source_dbs.values():
        sdb.close()
    db.close()
    print('Finished in {} seconds'.format(datetime.now() - start))
