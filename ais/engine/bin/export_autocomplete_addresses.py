import boto3
import botocore
import psycopg2
import petl as etl
from ais import app
from ais.util import parse_url

# Input params
config = app.config
read_db_string = config['DATABASES']['engine']
parsed_read_db_string = parse_url(read_db_string)
dbo = psycopg2.connect(
    "dbname={db_name} user={user}".format(db_name=parsed_read_db_string['db_name'], user=parsed_read_db_string['user']))

# Output params
s3_bucket = config['S3_BUCKET']
aws_profile = config['AWS_PROFILE']
autocomplete_addresses_path = 'autocomplete_addresses.csv'
autocomplete_addresses_old_path = str(autocomplete_addresses_path.split('.')[0]) + '_old.csv'

print("Selection addresses for autocomplete...")

stmt = '''
with valid_unit_sources as
(select distinct street_address
from source_address sa 
where source_name in 
('dor_condos', 'opa_property')
)
,
asum_units as 
(
select street_address 
from address_summary asum 
where unit_num != ''
)
,
all_condo_units as
(select distinct vus.*
from valid_unit_sources vus
inner join asum_units asum
on asum.street_address = vus.street_address
)
,
select_sources as
(select street_address 
from source_address 
where source_name not in ('AIS', 'dor_parcels')
)
,
non_units as
(
select * from address_summary
where unit_num = ''
)
,
non_unit_addresses as
(
select nu.street_address 
from select_sources ss
inner join non_units nu on nu.street_address = ss.street_address
)
,
all_base_addresses as
(select street_address 
from non_unit_addresses
union
select street_address
from source_address
where source_name = 'dor_parcels'
)
,
unioned as
(select street_address
from all_condo_units
union
select street_address
from all_base_addresses
)
select distinct street_address from unioned
order by street_address
'''
print("Getting addresses for autocomplete...")
autocomplete_addresses = etl.fromdb(dbo, stmt)
autocomplete_addresses.tocsv(autocomplete_addresses_path)

session = boto3.session.Session(profile_name=aws_profile)
s3 = session.resource('s3')
print("Renaming old address list in s3...")
s3.meta.client.copy_object(Bucket=s3_bucket, CopySource=s3_bucket + '/' + autocomplete_addresses_path, Key=autocomplete_addresses_old_path)
print("Writing autocomplete addresses to s3...")
s3.meta.client.upload_file(autocomplete_addresses_path, s3_bucket, autocomplete_addresses_path)
print("Completed writing autocomplete addresses to s3..."
# TODO: From here activate script on ec2 instance (alex-test) in same VPC as ElastiCache that will diff and update ElastiCache:



