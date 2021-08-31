#!/usr/bin/env bash

datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

echo "Activating virtual environment"
source ../../../env/bin/activate
source ../../../bin/eb_env_utils.sh

# GET LATEST CODE FROM GIT REPO
git fetch origin && git pull
cd ../../../env/src/passyunk
git fetch origin && git pull
cd -

# CREATE ENGINE LOG FILES
mkdir -p ../log
error_file="build_errors_"
out_file="build_log_"
error_file_loc=../log/$error_file$datestamp.txt
out_file_loc=../log/$out_file$datestamp.txt

# RUN BUILD ENGINE
echo "Building the engine."
send_teams "Starting new engine build."
bash build_engine.sh > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
send_teams "Engine build has completed."
end_dt=$(date +%Y%m%d%T)
echo "Time Summary: "
echo "Started: "$start_dt
echo "Finished: "$end_dt

# Get AWS production environment
echo "Finding the production environment"
eb_prod_env=$(get_prod_env EB_PROD_ENV || {
  echo "Could not find the production environment" ;
  exit 1 ;
})
echo "Production environment is: "$eb_prod_env

# Run tests
echo "Running engine tests."
send_teams "Running tests."
error_file_loc=../log/pytest_engine_errors_$datestamp.txt
out_file_loc=../log/pytest_engine_log_$datestamp.txt
pytest ../tests/test_engine.py > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
if [ $? -ne 0 ]
then
  echo "Engine tests failed"
  send_teams "Engine tests have failed."
  exit 1;
fi
send_teams "Engine tests have passed."

echo "Running API tests."
error_file_loc=../log/pytest_api_errors_$datestamp.txt
out_file_loc=../log/pytest_api_log_$datestamp.txt
pytest ../../api/tests/  > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
if [ $? -ne 0 ]
then
  echo "API tests failed"
  send_teams "API tests failed."
  exit 1;
fi
send_teams "API tests passed."

# Update (Restore) AWS RDS instance

# Make a copy (Dump) the newly built local engine db
echo "Copying the engine database."
send_teams "Copying the engine database."
mkdir -p ../backup
db_dump_file_loc=../backup/ais_engine.dump
pg_dump -Fc -U ais_engine -n public ais_engine > $db_dump_file_loc
if [ $? -ne 0 ]
then
  echo "DB dump failed"
  exit 1;
fi

# Get AWS staging environment
echo "Finding the staging environment"
eb_staging_env=$(get_staging_env EB_STAGING_ENV || {
  echo "Could not find the staging environment" ;
  exit 1 ;
})
echo "Staging environment is: "$eb_staging_env

# Get dsn of staging RDS
db_uri=$(get_db_uri $eb_staging_env || {
  echo "Could not find the db uri" ;
  exit 1 ;
})  
echo "Staging database uri: "$db_uri

echo "Restoring the engine DB into the $eb_staging_env environment "
send_teams "Restoring the engine DB into the "$eb_staging_env" environment."
psql -U ais_engine -h $db_uri -d ais_engine -c "DROP SCHEMA IF EXISTS public CASCADE;"
psql -U ais_engine -h $db_uri -d ais_engine -c "CREATE SCHEMA public;"
psql -U ais_engine -h $db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO postgres;"
psql -U ais_engine -h $db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO public;"
psql -U ais_engine -h $db_uri -d ais_engine -c "CREATE EXTENSION postgis;"
psql -U ais_engine -h $db_uri -d ais_engine -c "CREATE EXTENSION pg_trgm;"
pg_restore -h $db_uri -d ais_engine -U ais_engine -c $db_dump_file_loc

#if [ $? -ne 0 ]
#then
#  echo "DB restore failed"
#  exit 1;
#fi

# Warm up load balancer
echo "Warming up the load balancer."
send_teams "Warming up the load balancer."
python warmup_lb.py
if [ $? -ne 0 ]
then
  echo "Warmup failed"
  send_teams "AIS load balanacer warmup failed.\nEngine build has been pushed but not deployed."
  exit 1;
fi

# Set staging environment to swap
echo "Marking the $eb_staging_env environment as ready for deploy (swap)"
send_teams "Marking the "$eb_staging_env" environment as ready for deploy (swap)."
eb setenv -e $eb_staging_env SWAP=True --timeout 30

# Deploy latest code and swap
echo "Restarting the latest master branch build (requires travis CLI)"
if ! hash travis ; then
  echo "This step requires the Travis-CI CLI. To install and configure, see:
  https://github.com/travis-ci/travis.rb#installation"
  exit 1
fi

# Get last Travis build ID:
LAST_BUILD=$(travis history --com --branch master --limit 1 | cut --fields=1 --delimiter=" ")

# The build number has a number sign as the first character. We need to strip
# it off.
LAST_BUILD=${LAST_BUILD:1}
send_teams "Restarting the latest master branch build."
travis restart $LAST_BUILD --com
# NOTE: Travis-CI will take over from here. Check in the .travis/deploy script
# for further step.
if [ $? -ne 0 ]
then
  echo "Travis build failed"
  send_teams "Travis build failed.\nEngine build has been pushed but not deployed."
  exit 1;
fi
send_teams "New AIS build has been deployed."

# Reporting is called independently
#echo "Making engine reports."
#send_teams "Starting reporting."
#error_file_loc=../log/reports_errors_$datestamp.txt
#out_file_loc=../log/reports_log_$datestamp.txt
#python make_reports.py  > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
#if [ $? -ne 0 ]
#then
#  echo "Reports failed"
#  send_teams "Engine reports did not complete."
#  exit 1;
#fi
#send_teams "Engine reports have completed."

