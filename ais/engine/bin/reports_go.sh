#!/usr/bin/env bash

source config.sh

datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

echo "Activating virtual environment"
source ../../../env/bin/activate
source ../../../bin/eb_env_utils.sh

echo "Starting reporting."
send_teams "Starting reporting."

echo "Starting NG911 address points report..."
#send_teams "Starting NG911 address points report."
python output_address_points_for_ng911.py
if [ $? -ne 0 ]
then
  echo "Outputting address points for NG911 failed"
  send_teams "Engine reports did not complete."
  exit 1;
fi

python make_reports.py
if [ $? -ne 0 ]
then
  echo "Reporting has failed"
  send_teams "Engine reports did not complete."
  exit 1;
fi

bash output_spatial_tables.sh $POSTGIS_CONN $ORACLE_CONN_GIS_AIS
if [ $? -ne 0 ]
then
  echo "Reporting has failed"
  send_teams "Engine reports did not complete."
  exit 1;
fi

echo "Starting updating EPAM address points report."
python update_address_points.py
if [ $? -ne 0 ]
then
  echo "Reporting has failed"
  send_teams "Engine reports did not complete."
  exit 1;
fi

send_teams "Engine reports have completed."

end_dt=$(date +%Y%m%d%T)
echo finished at $end_dt


