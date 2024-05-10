import citygeo_secrets as cgs
import os
from os.path import expanduser

cgs.set_config(
    log_level='error',
    keeper_dir='~')

TEMP_ENV='citygeo_secrets_env_vars.bash'
INSERT_MARKER='# Below is automatically inserted by write-secrets-to-env.py'

cgs.generate_env_file('keeper', 
    RDS_ENGINE_DB_PASS = (
        'ais-engine (green and blue) - ais_engine',
        'password'),
    RDS_SUPER_ENGINE_DB_PASS = (
        'ais-engine (green and blue) - postgres',
        'password'),
    LOCAL_POSTGRES_ENGINE_DB_PASS = (
        'AIS local build postgres',
        'password'),
    LOCAL_ENGINE_DB_PASS = (
        'ais_engine/on-prem',
        'password'),
    AWS_ACCESS_KEY_ID = (
        'Citygeo AWS Key Pair PROD', 
        'access_key'), 
    AWS_SECRET_ACCESS_KEY = (
        'Citygeo AWS Key Pair PROD', 
        'secret_key')
    )

with open('.env', 'r') as f:
    lines = f.readlines()

# Find the index of the line that matches the insert_marker
insert_index = -1
for i, line in enumerate(lines):
    if line.strip() == INSERT_MARKER:
        insert_index = i
        break

# Truncate the file from the matched line onward
with open('.env', 'w') as f:
    f.writelines(lines[:insert_index+1])

# Append contents of the new file
with open(TEMP_ENV, 'r') as new_file:
    new_contents = new_file.read()

with open('.env', 'a') as f:
    f.write('\n' + new_contents)

os.remove(TEMP_ENV)

##############################
# Update ~/.aws/credentials

aws_creds = cgs.get_secrets('Citygeo AWS Key Pair PROD')
access_key_id       = aws_creds["Citygeo AWS Key Pair PROD"]['access_key']
secret_access_key   = aws_creds["Citygeo AWS Key Pair PROD"]['secret_key']

home = expanduser("~")

filename = os.path.join(home, '.aws/credentials')
with open(filename, 'r') as file:
    lines = file.readlines()

new_lines = []
for line in lines:
    if line.startswith('aws_access_key_id'):
        new_lines.append(f'aws_access_key_id = {access_key_id}\n')
    elif line.startswith('aws_secret_access_key'):
        new_lines.append(f'aws_secret_access_key = {secret_access_key}\n')
    else:
        new_lines.append(line)

with open(filename, 'w') as file:
    file.writelines(new_lines)

