import petl as etl
import cx_Oracle
import psycopg2
import geopetl
from datetime import datetime
from passyunk.parser import PassyunkParser
from ais import app


start = datetime.now()
print('Starting...')

"""SET UP"""

DEV = False
config = app.config
engine_dsn = config['DATABASES']['engine']
db_user = engine_dsn[engine_dsn.index("//") + 2:engine_dsn.index(":", engine_dsn.index("//"))]
db_pw = engine_dsn[engine_dsn.index(":",engine_dsn.index(db_user)) + 1:engine_dsn.index("@")]
db_name = engine_dsn[engine_dsn.index("/", engine_dsn.index("@")) + 1:]
pg_db = psycopg2.connect('dbname={db_name} user={db_user} password={db_pw} host=localhost'.format(db_name=db_name, db_user=db_user, db_pw=db_pw))
source_def = config['BASE_DATA_SOURCES']['address_points']['ng911_validated']
source_db_name = source_def['db']
source_db_url = config['DATABASES'][source_db_name]
source_dsn = source_db_url[source_db_url.index("//") + 2:]
source_user = source_dsn[:source_dsn.index(":")]
source_pw = source_dsn[source_dsn.index(":") + 1 : source_dsn.index("@")]
source_db = source_dsn[source_dsn.index("@") + 1:]
source_con = cx_Oracle.connect(source_user, source_pw, source_db)
source_table_name = source_def['table']
source_field_map = source_def['field_map']
source_where_condition = source_def['where']
source_field_map_upper = {}
source_fields = []
pg_write_table_name = 'ng911_address_points'

for k,v in source_field_map.items():
    source_field_map_upper[v] = k
    if v != 'shape':
        source_fields.append(v.upper())
# source_fields.remove('SHAPE')

#TODO: read source data, parse address and populate ng_911 table
print("Dropping indexes...")
pg_cur = pg_db.cursor()
pg_cur.execute('drop index if exists ix_ng911_address_points_street_address')
pg_cur.execute('truncate {}'.format(pg_write_table_name))
pg_db.commit()
print("Reading rows from source and writing to engine table {}...".format(pg_write_table_name))
etl.fromoraclesde(source_con, source_table_name, fields=source_fields, where=source_where_condition) \
    .rename(source_field_map_upper) \
    .progress(10000) \
    .topostgis(pg_db, pg_write_table_name)
print("Creating indexes...")
pg_cur.execute('''CREATE INDEX ix_ng911_address_points_street_address ON ng911_address_points USING btree (street_address)''')
pg_db.commit()
print("Time Elapsed: ", datetime.now() - start)