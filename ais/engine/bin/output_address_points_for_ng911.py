import psycopg2
import petl as etl
from ais import app
from ais.util import parse_url

config = app.config
target_table = 'ais.address_points_geocode_types_for_ng911'
temp_csv = 'output_address_points_for_ng911.csv'

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
outputquery = 'COPY ({export_stmt}) TO STDOUT WITH CSV HEADER'.format(export_stmt=export_stmt)

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

with open(temp_csv, 'r') as f:
    with target_conn.cursor() as cursor:
        copy_stmt = '''
        BEGIN;
        TRUNCATE TABLE {target_table};
        COPY {target_table} ({str_header}) FROM STDIN WITH (FORMAT csv, HEADER true);
        COMMIT;
        '''.format(target_table=target_table, str_header=str_header)
        cursor.copy_expert(copy_stmt, f)
        
target_conn.close()