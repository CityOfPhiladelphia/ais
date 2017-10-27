#!/usr/bin/env bash

datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

echo "Activating virtual environment"
source ../../../env/bin/activate
source ../../../bin/eb_env_utils.sh

echo "Starting reporting."
send_slack "Starting reporting."

python make_reports.py
if [ $? -ne 0 ]
then
  echo "Reporting has failed"
  send_slack "Engine reports did not complete."
  exit 1;
fi
send_slack "Engine reports have completed."

end_dt=$(date +%Y%m%d%T)
echo finished at $end_dt


