import sys
import traceback
from datetime import datetime
import petl as etl
import geopetl
import cx_Oracle
import psycopg2
#from pprint import pprint
# from phladdress.parser import Parser
from ais import app
from datum import Database
from ais.models import StreetIntersection


print('Starting...')
start = datetime.now()

"""SET UP"""

config = app.config
engine_srid = config['ENGINE_SRID']
Parser = config['PARSER']
db = Database(config['DATABASES']['engine'])
dsn = config['DATABASES']['engine']
db_user = dsn[dsn.index("//") + 2:dsn.index(":", dsn.index("//"))]
db_pw = dsn[dsn.index(":",dsn.index(db_user)) + 1:dsn.index("@")]
db_name = dsn[dsn.index("/", dsn.index("@")) + 1:]
pg_db = psycopg2.connect('dbname={db_name} user={db_user} password={db_pw} host=localhost'.format(db_name=db_name, db_user=db_user, db_pw=db_pw))

# Get table params
source_def = config['BASE_DATA_SOURCES']['streets']
source_db_name = source_def['db']
source_db_url = config['DATABASES'][source_db_name]
field_map = source_def['field_map']
centerline_table_name = source_def['table']
nodes_table_name = 'GIS_STREETS.Street_Nodes'
street_full_fields = ['street_' + x for x in ['predir', 'name', 'suffix', 'postdir']]
source_street_full_fields = [field_map[x] for x in street_full_fields]
con_dsn = source_db_url[source_db_url.index("//") + 2:]
con_user = con_dsn[:con_dsn.index(":")]
con_pw = con_dsn[con_dsn.index(":") + 1 : con_dsn.index("@")]
con_db = con_dsn[con_dsn.index("@") + 1:]
con = cx_Oracle.connect(con_user, con_pw, con_db)
# Get table references
source_db = Database(source_db_url)
centerline_table = source_db[centerline_table_name]
node_table = source_db[nodes_table_name]
source_geom_field = centerline_table.geom_field
intersection_table_name = StreetIntersection.__table__.name
intersection_table = db[intersection_table_name]


"""MAIN"""

parser = Parser()

print('Deleting existing intersections...')
intersection_table.delete(cascade=True)

print('Creating temporary tables...')

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
      street_type text,
      fnode numeric(10,0),
      tnode numeric(10,0),
      geom geometry(MultiLineString, 2272)
);
'''
db.execute(st_cent_stmt)
db.save()

st_node_stmt = '''
    DROP table if exists street_nodes;
    CREATE TABLE public.street_nodes
    (
      objectid numeric(10,0),
      streetcl_ numeric(10,0),
      node_id numeric(10,0),
      int_id numeric(10,0),
      intersecti character varying(255),
      geom geometry(Point,2272),
      CONSTRAINT street_nodes_pkey PRIMARY KEY (objectid)
);
'''
db.execute(st_node_stmt)
db.save()

print('Reading streets from source...')
source_fields = list(field_map.values())
# where = "st_type != 'RAMP'"
centerline_rows = centerline_table.read(to_srid=engine_srid)
centerlines = []
nodes = []
error_count = 0

for i, cl_row in enumerate(centerline_rows):
    try:
        if i % 10000 == 0:
            print(i)

        # Parse street name
        source_street_full_comps = [str(cl_row[x]).strip() for x in \
                                    source_street_full_fields]
        source_street_full_comps = [x for x in source_street_full_comps if x != '']
        source_street_full = ' '.join(source_street_full_comps)
        seg_id = cl_row[field_map['seg_id']]
        parsed = None
        try:
            parsed = parser.parse(source_street_full)
            if parsed['type'] != 'street':
                raise ValueError('Invalid street')

            # comps = parsed['components']    			<== phladdress
            comps = parsed['components']['street']  # <== passyunk
        except:
            pass
        # Test with this version allowing all nodes in (including ramps, etc.) - if troublesome remove
        # except Exception as e:
        #     raise ValueError('Could not parse')
        if parsed['type'] == 'street':
            street_comps = {
                'street_predir': comps['predir'] or '',
                'street_name': comps['name'] or '',
                'street_suffix': comps['suffix'] or '',
                'street_postdir': comps['postdir'] or '',
                'street_full': comps['full'],
            }
        else:
            print(source_street_full)
            street_comps = {
            # 'street_predir': cl_row[field_map['street_predir']] or '',
            # 'street_name': cl_row[field_map['street_name']] or '',
            # 'street_suffix': cl_row[field_map['street_suffix']] or '',
            # 'street_postdir': cl_row[field_map['street_postdir']] or '',
            'street_full': source_street_full,
            }

        centerline = {key: cl_row[value] for key, value in field_map.items()}
        centerline.update(street_comps)
        centerline['geom'] = cl_row[source_geom_field]
        centerline['fnode'] = cl_row['fnode_']
        centerline['tnode'] = cl_row['tnode_']
        centerline['street_type'] = cl_row['st_type']
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

centerline_table = db['street_centerlines']
nodes_table = db['street_nodes']
print(nodes_table)

'''
WRITE
'''
print("Copying temporary street_nodes table...")
etl.fromoraclesde(con, nodes_table_name, fields=['objectid', 'streetcl_', 'node_id', 'int_id', 'intersecti'])\
    .rename({'shape': 'geom'})\
    .topostgis(pg_db, 'street_nodes')

print("Writing temporary centerline table...")
centerline_table.write(centerlines, chunk_size=50000)

intersections = []
error_count = 0

st_int_stmt =\
'''
with distinct_st1scns as
(
	select distinct *
	from
	(
	with scsn as (
	select sn.*, sc.street_code
	from street_nodes sn
	left join street_centerlines sc on sc.tnode = sn.node_id
	union
	select sn.*, sc.street_code
	from street_nodes sn
	left join street_centerlines sc on sc.fnode = sn.node_id	)
	,
	scsn_distinct as
	(select distinct on (node_id, street_code) *
	from scsn
	)
	,
	scsnd_join as
	(select scsnd.*, scsn.street_code as st_code_2
	from scsn_distinct scsnd
	left join scsn on scsn.node_id = scsnd.node_id and scsn.street_code != scsnd.street_code
	)
	,
	scsndj_distinct as
	(
	select objectid, node_id, int_id, intersecti, geom, street_code as street_1_code, st_code_2 as street_2_code
	from scsnd_join
	where street_code < st_code_2
	union
	select objectid, node_id, int_id, intersecti, geom, street_code as street_1_code, st_code_2 as street_2_code
	from scsnd_join
	where (street_code is null or st_code_2 is null) and not (street_code is null and st_code_2 is null)
	order by int_id
	)
	,
	scsndjd_distinct as
	(
	select distinct on (int_id, street_1_code, street_2_code) *
	from scsndj_distinct
	)
	select scsn.*, sc.street_predir as street_1_predir, sc.street_name as street_1_name, sc.street_suffix as street_1_suffix, sc.street_postdir as street_1_postdir, sc.street_full as street_1_full, sc.street_type as street_1_type
	from scsndjd_distinct scsn
	left join street_centerlines sc on sc.street_code = scsn.street_1_code
	order by scsn.node_id
	) st1cns
	order by node_id
)
,
st12scns as
(
select scsn1.*, sc.street_predir as street_2_predir, sc.street_name as street_2_name, sc.street_suffix as street_2_suffix, sc.street_postdir as street_2_postdir, sc.street_full as street_2_full, sc.street_type as street_2_type
from distinct_st1scns scsn1
left join street_centerlines sc on sc.street_code = street_2_code
order by scsn1.node_id
)
,
final AS
(
select distinct node_id, int_id, street_1_code, street_1_name, street_1_full, street_1_predir, street_1_postdir, street_1_suffix,
  street_2_code, street_2_name, street_2_full, street_2_predir, street_2_postdir, street_2_suffix, geom
from st12scns
WHERE int_id is not NULL and street_1_type != 'RAMP' and street_2_type != 'RAMP'
order by node_id
)
INSERT INTO street_intersection (node_id, int_id, street_1_code, street_1_name, street_1_full, street_1_predir, street_1_postdir, street_1_suffix, street_2_code,
street_2_name, street_2_full, street_2_predir, street_2_postdir, street_2_suffix, geom)
    (SELECT final.node_id, final.int_id, final.street_1_code, final.street_1_name, final.street_1_full, final.street_1_predir, final.street_1_postdir,
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

print("Deleting temporary nodes table...")
del_st_node_stmt =\
'''
    Drop table if exists street_nodes;
'''
db.execute(del_st_node_stmt)
db.save()
'''
FINISH
'''

#source_db.close()
db.close()
print('Finished in {} seconds'.format(datetime.now() - start))
