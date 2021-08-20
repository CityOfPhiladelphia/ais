import petl as etl
import cx_Oracle
import psycopg2
import geopetl
from ais import app

config = app.config

# read opa_active_accounts from databridge (oracle sde) and write to engine (postgis)

# Get source table connection
source_def = config['BASE_DATA_SOURCES']['opa_active_accounts']
source_db_name = source_def['db']
source_db_url = config['DATABASES'][source_db_name]
source_field_map = source_def['field_map']
#source_fields = '{}'.format(','.join(list(source_field_map.values()))).upper()
source_fields = [field for field in list(source_field_map.values()) if field != 'shape']
print(source_fields)
conn_dsn = source_db_url[source_db_url.index("//") + 2:]
conn_user = conn_dsn[:conn_dsn.index(":")]
conn_pw = conn_dsn[conn_dsn.index(":") + 1 : conn_dsn.index("@")]
conn_db = conn_dsn[conn_dsn.index("@") + 1:]
source_conn = cx_Oracle.connect(conn_user, conn_pw, conn_db)
source_table_schema_name = 'GIS_OPA.OPA_ACTIVE_ACCOUNTS'

target_dsn = config['DATABASES']['engine']
target_user = target_dsn[target_dsn.index("//") + 2:target_dsn.index(":", target_dsn.index("//"))]
target_pw = target_dsn[target_dsn.index(":",target_dsn.index(target_user)) + 1:target_dsn.index("@")]
target_name = target_dsn[target_dsn.index("/", target_dsn.index("@")) + 1:]
target_conn = psycopg2.connect('dbname={db_name} user={db_user} password={db_pw} host=localhost'.format(db_name=target_name, db_user=target_user, db_pw=target_pw))
target_cur = target_conn.cursor()
target_table_name = 'public.t_opa_active_accounts'
print("target_table_name: ", target_table_name)

# Read source table:
rows = etl.fromoraclesde(source_conn, source_table_schema_name, fields=source_fields)
print(etl.look(rows))
# Format fields
rows = rows.rename({v:k for k,v in source_field_map.items()})
print(etl.look(rows))

drop_stmt = '''drop table if exists {}'''.format(target_table_name)
create_stmt = '''create table {} (
               account_num text,
               source_address text,
               unit_num text,
               geom geometry(Point,2272)
)'''.format(target_table_name)
# Create temp target table:
target_cur.execute(drop_stmt)
target_cur.execute(create_stmt)
target_conn.commit()
# Write rows to target:
rows.topostgis(target_conn, target_table_name)

# Update address_parcel by selecting address from opa_property associated with opa_account_num for opa_active_accounts record where opa_address doesn't have pwd_parcel in table, \
# and add row_id of parcel based on associated pwd_parcel_id in opa_active_accounts table:

update_stmt = '''
insert into address_parcel (street_address, parcel_source, parcel_row_id, match_type)
select distinct opanopp.street_address, 'pwd' as parcel_source, pp.id, 'manual' as match_type
from
(
 select nopp.street_address, opaaa.account_num, opaaa.geom
 from opa_property opa
 inner join (
		select street_address
		from opa_property
	except (
		select street_address
		from address_parcel
		where parcel_source = 'pwd' and parcel_row_id is not null
	)
 ) nopp on nopp.street_address = opa.street_address
 inner join t_opa_active_accounts opaaa on opaaa.account_num = opa.account_num
) opanopp inner join pwd_parcel pp on st_intersects(opanopp.geom, pp.geom)
'''

target_cur.execute(update_stmt)
target_conn.commit()

# drop temp table:
target_cur.execute(drop_stmt)
target_conn.commit()

# close db connection:
target_conn.close()
