import requests
import json
import psycopg2
import petl as etl
from ais import app
from ais.util import parse_url

############################
# This script extracts NG911 geometry (proxy for the front door) for each address point and writes
# it to the databridge-raw database, table name "ais.address_points_geocode_types_for_ng911"
# Then, triggers a DAG that upserts records in the tripoli 911 database

config = app.config
target_table = 'ais.address_points_geocode_types_for_ng911'
temp_csv = 'output_address_points_for_ng911.csv'
airflow_trigger_creds = config['AIRFLOW_TRIGGER_CREDS']

# Make source connection
source_db_string = config['DATABASES']['engine']
parsed_source_db_string = parse_url(source_db_string)
source_conn = psycopg2.connect(
    dbname=parsed_source_db_string['db_name'], 
    user=parsed_source_db_string['user'], 
    password=parsed_source_db_string['password'], 
    host=parsed_source_db_string['host']
    )

# Make target connection
target_db_string = config['DATABASES']['ng911_transform']
parsed_target_db_string = parse_url(target_db_string)
target_conn = psycopg2.connect(
    dbname=parsed_target_db_string['db_name'], 
    user=parsed_target_db_string['user'], 
    password=parsed_target_db_string['password'], 
    host=parsed_target_db_string['host']
    )

# Export source data to temp csv:
print("Exporting source rows...")
export_stmt = '''
    select distinct prep.street_address, 
    case when gp.geom is not null then ST_AsEWKT(gp.geom)
    when gd.geom is not null then ST_AsEWKT(gd.geom)
    else ST_AsEWKT(st_setsrid(st_makepoint(prep.geocode_x, prep.geocode_y), 2272)) end as geom,
    case when gp.geocode_type is not null then 'pwd_parcel_front'
    when gd.geocode_type is not null then 'dor_parcel_front'
    else prep.geocode_type end as geocode_type
    from (
        select distinct s.street_address, asum.geocode_type, asum.geocode_x, asum.geocode_y
        from (
        select distinct street_address from source_address where source_name in (
            'pwd_accounts','dor_condos', 'dor_parcels','zoning_documents', 'pwd_parcels', 'opa_property', 'li_eclipse_location_ids', 'building_footprints', 'voters'
            )
        ) s
        join address_summary asum on asum.street_address = s.street_address
    ) prep
    left join geocode gp on gp.geocode_type = 11 and gp.street_address = prep.street_address
    left join geocode gd on gd.geocode_type = 12 and gd.street_address = prep.street_address
'''

source_cur = source_conn.cursor()
outputquery = f'COPY ({export_stmt}) TO STDOUT WITH CSV HEADER'

with open(temp_csv, "w") as f:
    with source_conn.cursor() as cursor:
        cursor.copy_expert(outputquery, f)
source_conn.close()

# Write to target table

# form a header string for insert stmt
print("Updating target table...")
rows = etl.fromcsv(temp_csv)
header = rows[0]
str_header = ''
num_fields = len(header)
for i, field in enumerate(header):
    if i < num_fields - 1:
        str_header += field + ', '
    else:
        str_header += field

with open(temp_csv, 'r') as file:
    with target_conn.cursor() as cursor:
        copy_stmt = f'''
        BEGIN;
        TRUNCATE TABLE {target_table};
        COPY {target_table} ({str_header}) FROM STDIN WITH (FORMAT csv, HEADER true);
        COMMIT;
        '''
        cursor.copy_expert(copy_stmt, file)

target_conn.close()

# Trigger DAG to update NG911:
workflow = 'etl_ng911_v0'
print(f"Triggering downstream DAG {workflow}...")
try:
    r = requests.post(
        airflow_trigger_creds.get('url').format(dag_name=workflow),
        data=json.dumps("{}".format('{}')),
        auth=(f"{airflow_trigger_creds.get('user')}", f"{airflow_trigger_creds.get('pw')}")
    )
    print(f"Downstream process has been triggered, status code: {r.status_code}")
except Exception as e:
    print("Triggering downstream process failed, exiting")
    raise e
