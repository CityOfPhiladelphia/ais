
import cx_Oracle
import petl as etl
import geopetl
from ais import app
from ais.util import parse_url

config = app.config
write_account = 'gis_ais'
write_db_string = config['DATABASES']['gis_ais']
parsed_write_db_string = parse_url(write_db_string)
write_dsn = parsed_write_db_string['user'] + '/' + parsed_write_db_string['password'] + '@' + parsed_write_db_string[
    'host']
write_conn = cx_Oracle.connect(write_dsn)

address_points_sp = 'SP_REFRESH_ADDR_PTS_FOR_EPAM'
sql = ''' CALL {write_account}.{address_points_sp}()'''.format(write_account=write_account, address_points_sp=address_points_sp)

cur = write_conn.cursor()
cur.execute(sql)
write_conn.commit()
write_conn.close()