#!/usr/bin/env bash

datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

# GET LATEST CODE FROM GIT REPO
git fetch origin && git pull

# CREATE ENGINE LOG FILES
mkdir -p ../log
error_file="build_errors_"
out_file="build_log_"
error_file_loc=../log/$error_file$datestamp.txt
out_file_loc=../log/$out_file$datestamp.txt

# RUN BUILD ENGINE
echo "Building the engine."
bash build_engine.sh > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
end_dt=$(date +%Y%m%d%T)
echo "Time Summary: "
echo "Started: "$start_dt
echo "Finished: "$end_dt

# Get AWS production environment
echo "Finding the production environment"
source ../../../bin/eb_env_utils.sh
get_prod_env EB_PROD_ENV || {
  echo "Could not find the production environment" ;
  exit 1 ;
}

# Run tests
echo "Running engine tests."
error_file_loc=../log/pytest_engine_errors_$datestamp.txt
out_file_loc=../log/pytest_engine_log_$datestamp.txt
pytest ../tests/test_engine.py $EB_PROD_ENV > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
if [ $? -ne 0 ]
then
  echo "Engine tests failed"
  exit 1;
fi

echo "Running API tests."
error_file_loc=../log/pytest_api_errors_$datestamp.txt
out_file_loc=../log/pytest_api_log_$datestamp.txt
pytest ../../api/tests/  > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
if [ $? -ne 0 ]
then
  echo "API tests failed"
  exit 1;
fi

# Make a copy (Dump) the newly built local engine db
echo "Copying the engine database."
mkdir -p ../backup
db_dump_file_loc=../backup/ais_engine.dump
pg_dump -Fc -U ais_engine -n public ais_engine > $db_dump_file_loc

# Update (Restore) AWS RDS instance

# Get AWS staging environment
echo "Finding the staging environment"
source ../../../bin/eb_env_utils.sh
get_staging_env EB_STAGING_ENV || {
  echo "Could not find the staging environment" ;
  exit 1 ;
}
# Get dsn of staging RDS
db_uri=$(get_db_uri $EB_STAGING_ENV)

