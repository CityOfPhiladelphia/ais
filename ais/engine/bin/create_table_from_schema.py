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
sql0 = "DROP TABLE t_{}".format(table_name)
sql1 = "CREATE TABLE t_{table_name} as (select * from {table_name} where 1=0)".format(table_name=table_name)
sql2 = "GRANT SELECT on t_{} to SDE".format(table_name)
sql3 = "GRANT SELECT ON t_{} to GIS_SDE_VIEWER".format(table_name)
sql4 = "GRANT SELECT ON t_{} to GIS_AIS_SOURCES".format(table_name)
if table_name == 'address_summary':
    sql5 = "GRANT SELECT on t_{} to GIS_OPA with GRANT OPTION".format(table_name)
elif table_name == 'dor_parcel_address_check':
    sql5 = "GRANT SELECT ON t_{} to GIS_DOR".format(table_name)
curs.execute(sql1)
curs.execute(sql2)
curs.execute(sql3)
curs.execute(sql4)
curs.execute(sql5)
conn.commit()
