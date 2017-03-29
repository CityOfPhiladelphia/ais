import sys
import traceback
from datetime import datetime
#from pprint import pprint
# from phladdress.parser import Parser
from ais import app
from datum import Database
from ais.models import StreetIntersection


print('Starting...')
start = datetime.now()

"""SET UP"""

config = app.config
Parser = config['PARSER']
db = Database(config['DATABASES']['engine'])
engine_srid = config['ENGINE_SRID']

# Get table params
source_def = config['BASE_DATA_SOURCES']['streets']
source_db_name = source_def['db']
source_db_url = config['DATABASES'][source_db_name]
field_map = source_def['field_map']
source_table_name = source_def['table']
street_full_fields = ['street_' + x for x in ['predir', 'name', 'suffix', 'postdir']]
source_street_full_fields = [field_map[x] for x in street_full_fields]

# Get table references
source_db = Database(source_db_url)
source_table = source_db[source_table_name]
source_geom_field = source_table.geom_field
intersection_table_name = StreetIntersection.__table__.name
intersection_table = db[intersection_table_name]


"""MAIN"""

parser = Parser()

print('Deleting existing intersections...')
intersection_table.delete(cascade=True)

print('Reading streets from source...')
source_fields = list(field_map.values())
source_rows = source_table.read(to_srid=engine_srid)
centerlines = []
error_count = 0

for i, source_row in enumerate(source_rows):
    try:
        if i % 10000 == 0:
            print(i)

        # Parse street name
        source_street_full_comps = [str(source_row[x]).strip() for x in \
                                    source_street_full_fields]
        source_street_full_comps = [x for x in source_street_full_comps if x != '']
        source_street_full = ' '.join(source_street_full_comps)
        seg_id = source_row[field_map['seg_id']]
        try:
            parsed = parser.parse(source_street_full)
            if parsed['type'] != 'street':
                raise ValueError('Invalid street')

            # comps = parsed['components']    			<== phladdress
            comps = parsed['components']['street']  # <== passyunk
        except Exception as e:
            raise ValueError('Could not parse')

        street_comps = {
            'street_predir': comps['predir'] or '',
            'street_name': comps['name'] or '',
            'street_suffix': comps['suffix'] or '',
            'street_postdir': comps['postdir'] or '',
            'street_full': comps['full'],
        }

        centerline = {key: source_row[value] for key, value in field_map.items()}
        centerline.update(street_comps)
        centerline['geom'] = source_row[source_geom_field]
        centerline.pop('left_to', None)
        centerline.pop('left_from', None)
        centerline.pop('right_to', None)
        centerline.pop('right_from', None)
        centerline.pop('seg_id', None)
        centerlines.append(centerline)

    except ValueError as e:
        # FEEDBACK
        print('{}: {} ({})'.format(e, source_street_full, seg_id))
        error_count += 1

    except Exception as e:
        print('Unhandled error on row: {}'.format(i))
        # pprint(street)
        print(traceback.format_exc())
        sys.exit()

st_cent_stmt = '''
    DROP table if exists street_centerlines;
    Create table street_centerlines
    (
      street_code numeric(10,0),
      street_name text,
      street_full text,
      street_predir text,
      street_postdir text,
      street_suffix text,
      geom geometry(MultiLineString, 2272)
);
'''
db.execute(st_cent_stmt)
db.save()

centerline_table = db['street_centerlines']
'''
WRITE
'''
print("Writing temporary centerline table...")
centerline_table.write(centerlines, chunk_size=50000)

intersections = []
error_count = 0

st_int_stmt =\
'''
with sts as
(select street_code as st_code, street_name, street_full, street_predir, street_postdir, street_suffix,
    ST_Union(geom) as geom from street_centerlines
group by st_code, street_name, street_full, street_predir, street_postdir, street_suffix),
test_intersections as
(
select sts1.st_code as street_1_code, sts2.st_code as street_2_code, sts1.street_name as street_1_name,
sts2.street_name as street_2_name, sts1.street_full as street_1_full, sts2.street_full as street_2_full,
sts1.street_predir as street_1_predir, sts2.street_predir as street_2_predir,
sts1.street_postdir as street_1_postdir, sts2.street_postdir as street_2_postdir, sts1.street_suffix as street_1_suffix,
sts2.street_suffix as street_2_suffix, ST_Intersection(sts1.geom, sts2.geom) as geom
from sts sts1
left join sts sts2 on ST_Intersects(sts2.geom, sts1.geom) AND sts2.st_code != sts1.st_code
),
points as (
select *
from test_intersections
where GeometryType(geom) = 'POINT'
),
multi_points as (
select *
from test_intersections
where GeometryType(geom) = 'MULTIPOINT'
),
mpps as (
select street_1_code, street_1_name, street_1_full, street_1_predir, street_1_postdir, street_1_suffix, street_2_code,
street_2_name, street_2_full, street_2_predir, street_2_postdir, street_2_suffix, (st_dumppoints).geom as geom
from
(select street_1_code, street_1_name, street_1_full, street_1_predir, street_1_postdir, street_1_suffix, street_2_code,
street_2_name, street_2_full, street_2_predir, street_2_postdir, street_2_suffix, ST_DumpPoints(geom)
from multi_points)foo
),
combined as (
select geom, street_1_code, street_1_name, street_1_full, street_1_predir, street_1_postdir, street_1_suffix, street_2_code,
street_2_name, street_2_full, street_2_predir, street_2_postdir, street_2_suffix
from points
union
select geom, street_1_code, street_1_name, street_1_full, street_1_predir, street_1_postdir, street_1_suffix, street_2_code,
street_2_name, street_2_full, street_2_predir, street_2_postdir, street_2_suffix
from mpps
),
final as
(
select distinct on (foo.street_1_code, foo.street_2_code, foo.geom) foo.street_1_code, foo.street_1_name,
foo.street_1_full, foo.street_1_predir, foo.street_1_postdir, foo.street_1_suffix, foo.street_2_code,
foo.street_2_name, foo.street_2_full, foo.street_2_predir, foo.street_2_postdir, foo.street_2_suffix, foo.geom
from
(select geom,

CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_2_code ELSE street_1_code END AS street_1_code
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_2_full ELSE street_1_full END AS street_1_full
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_2_name ELSE street_1_name END AS street_1_name
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_2_predir ELSE street_1_predir END AS street_1_predir
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_2_postdir ELSE street_1_postdir END AS street_1_postdir
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_2_suffix ELSE street_1_suffix END AS street_1_suffix
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_1_code ELSE street_2_code END AS street_2_code
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_1_full ELSE street_2_full END AS street_2_full
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_1_name ELSE street_2_name END AS street_2_name
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_1_predir ELSE street_2_predir END AS street_2_predir
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_1_postdir ELSE street_2_postdir END AS street_2_postdir
,CASE WHEN street_2_code = LEAST(street_1_code, street_2_code) THEN street_1_suffix ELSE street_2_suffix END AS street_2_suffix
from combined
ORDER BY street_1_code
)foo
)
INSERT INTO street_intersection (street_1_code, street_1_name, street_1_full, street_1_predir, street_1_postdir, street_1_suffix, street_2_code,
street_2_name, street_2_full, street_2_predir, street_2_postdir, street_2_suffix, geom)
    (SELECT final.street_1_code, final.street_1_name, final.street_1_full, final.street_1_predir, final.street_1_postdir,
    final.street_1_suffix, final.street_2_code, final.street_2_name, final.street_2_full, final.street_2_predir,
    final.street_2_postdir, final.street_2_suffix, final.geom from final)
;
'''

print("Writing street intersection table...")
db.execute(st_int_stmt)
db.save()

print("Deleting temporary centerline table...")
del_st_cent_stmt =\
'''
    Drop table if exists street_centerlines;
'''
db.execute(del_st_cent_stmt)
db.save()
'''
FINISH
'''

source_db.close()
db.close()
print('Finished in {} seconds'.format(datetime.now() - start))