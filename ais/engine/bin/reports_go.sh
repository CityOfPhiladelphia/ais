#!/usr/bin/env bash

datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

echo "Activating virtual environment"
WORKING_DIRECTORY=/home/ubuntu/ais
echo "Working directory is $WORKING_DIRECTORY"
cd $WORKING_DIRECTORY

source $WORKING_DIRECTORY/venv/bin/activate
source $WORKING_DIRECTORY/bin/eb_env_utils.sh

echo "Starting reporting."
send_teams "Starting reporting."

##################################################
# TEMPORARY COMMENT OUT UNTIL WE'RE IN PRODUCTION 
# -Roland 7/27/2023
#echo "Starting NG911 address points report..."
#send_teams "Starting NG911 address points report."

#python $WORKING_DIRECTORY/ais/engine/bin/output_address_points_for_ng911.py
#if [ $? -ne 0 ]
#then
#  echo "Outputting address points for NG911 failed"
#  send_teams "Engine reports did not complete."
#  exit 1;
#fi
##################################################

python $WORKING_DIRECTORY/ais/engine/bin/make_reports.py
if [ $? -ne 0 ]
then
  echo "Reporting has failed"
  send_teams "Engine reports did not complete."
  exit 1;
fi
echo "Engine reports have completed."
send_teams "Engine reports have completed."

end_dt=$(date +%Y%m%d%T)
echo finished at $end_dt


