#!/usr/bin/env bash

datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

error_file="build_errors_"
out_file="build_log_"
error_file_loc=../log/$error_file$datestamp.txt
out_file_loc=../log/$out_file$datestamp.txt

mkdir -p ../log

bash build_engine.sh > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)

end_dt=$(date +%Y%m%d%T)

echo "Time Summary: "
echo "Started: "$start_dt
echo "Finished: "$end_dt

echo "Finding the production environment"
source ../../../bin/eb_env_utils.sh
get_prod_env EB_PROD_ENV || {
  echo "Could not find the production environment" ;
  exit 1 ;
}

error_file_loc=../log/pytest_engine_errors_$datestamp.txt
out_file_loc=../log/pytest_engine_log_$datestamp.txt
pytest ../tests/test_engine.py $EB_PROD_ENV > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)


if [ $? -ne 0 ]
then
  echo "Engine tests failed"
  exit 1;
fi

error_file_loc=../log/pytest_api_errors_$datestamp.txt
out_file_loc=../log/pytest_api_log_$datestamp.txt
pytest ../../api/tests/  > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)

if [ $? -ne 0 ]
then
  echo "API tests failed"
  exit 1;
fi
