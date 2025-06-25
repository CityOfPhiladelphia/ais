# TODO: migrate file from Oracle or remove if unnecessary
import sys
import cx_Oracle
from ais import app

table_name = sys.argv[1]
dsn_map = {
    'address_summary': 'GIS_AIS_CONN',
    'dor_parcel_address_check': 'GIS_AIS_CONN'
}
config = app.config
dsn = config[dsn_map[table_name]]
conn = cx_Oracle.connect(dsn)
curs = conn.cursor()
sql0 = f"DROP TABLE t_{table_name}"
sql1 = f"CREATE TABLE t_{table_name} as (select * from {table_name} where 1=0)"
sql2 = f"GRANT SELECT on t_{table_name} to SDE"
sql3 = f"GRANT SELECT ON t_{table_name} to GIS_SDE_VIEWER"
sql4 = f"GRANT SELECT ON t_{table_name} to GIS_AIS_SOURCES"
if table_name == 'address_summary':
    sql5 = f"GRANT SELECT on t_{table_name} to GIS_OPA with GRANT OPTION"
elif table_name == 'dor_parcel_address_check':
    sql5 = f"GRANT SELECT ON t_{table_name} to GIS_DOR"
curs.execute(sql1)
curs.execute(sql2)
curs.execute(sql3)
curs.execute(sql4)
curs.execute(sql5)
conn.commit()
