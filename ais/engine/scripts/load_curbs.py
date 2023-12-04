from datetime import datetime
import datum
from ais import app

def main():
    print('Starting...')
    start = datetime.now()

    """SET UP"""

    config = app.config
    source_def = config['BASE_DATA_SOURCES']['curbs']
    source_db = datum.connect(config['DATABASES'][source_def['db']])
    source_table = source_db[source_def['table']]
    field_map = source_def['field_map']
    db = datum.connect(config['DATABASES']['engine'])
    curb_table = db['curb']
    parcel_curb_table = db['parcel_curb']

    """MAIN"""

    print('Dropping indexes...')
    curb_table.drop_index('curb_id')
    parcel_curb_table.drop_index('curb_id')
    parcel_curb_table.drop_index('parcel_source', 'parcel_row_id')

    print('Deleting existing curbs...')
    curb_table.delete()

    print('Deleting existing parcel curbs...')
    parcel_curb_table.delete()

    print('Reading curbs from source...')
    source_rows = source_table.read()
    curbs = []
    for source_row in source_rows:
        curb = {x: source_row[field_map[x]] for x in field_map}
        curbs.append(curb)

    print('Writing curbs...')
    curb_table.write(curbs)

    print('Making parcel-curbs...')
    for agency in config['BASE_DATA_SOURCES']['parcels']:
        print('  - ' + agency)
        stmt = '''
            insert into parcel_curb (parcel_source, parcel_row_id, curb_id) (
              select distinct on (p.id)
                '{agency}',
                p.id,
                c.curb_id
              from {agency}_parcel p
              join curb c
              on ST_Intersects(p.geom, c.geom)
              order by p.id, st_area(st_intersection(p.geom, c.geom)) desc
         )
        '''.format(agency=agency)
        db.execute(stmt)
        db.save()

    print('Creating indexes...')

    db.close()
    print('Finished in {} seconds'.format(datetime.now() - start))
    
