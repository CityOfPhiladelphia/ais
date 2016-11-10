import sys
import traceback
from datetime import datetime
from pprint import pprint
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

for source_row in source_rows:
    centerline = {'street_code': source_row['st_code']}
    centerline['geom'] = source_row[source_geom_field]
    centerlines.append(centerline)

st_cent_stmt = '''
    DROP table if exists street_centerlines;
    Create table street_centerlines
    (
      street_code numeric(10,0),
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

streets = []
error_count = 0

st_int_stmt =\
'''
with sts as
(select street_code as st_code, ST_Union(geom) as geom from street_centerlines
group by st_code),
test_intersections as
(
select sts1.st_code as st_code_1, sts2.st_code as st_code_2, ST_Intersection(sts1.geom, sts2.geom) as geom
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
select st_code_1, st_code_2, (st_dumppoints).geom as geom
from
(select st_code_1, st_code_2, ST_DumpPoints(geom)
from multi_points)foo
),
combined as (
select geom, st_code_1, st_code_2
from points
union
select geom, st_code_1, st_code_2
from mpps
),
final as
(
select distinct foo.st_code_1, foo.st_code_2, foo.geom
from
(
select LEAST(st_code_1, st_code_2) as st_code_1, GREATEST(st_code_1, st_code_2) as st_code_2, geom
from combined
ORDER BY st_code_1
)foo
)
INSERT INTO street_intersection (street_code_1, street_code_2, geom)
    (SELECT final.st_code_1, final.st_code_2, final.geom from final)
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