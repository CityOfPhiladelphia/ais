#!/usr/bin/env bash
set -e

WORKING_DIRECTORY=/home/ubuntu/ais
cd $WORKING_DIRECTORY

export ORACLE_HOME=/usr/lib/oracle/18.5/client64
export PATH=$PATH:$ORACLE_HOME/bin
export LD_LIBRARY_PATH=$ORACLE_HOME/lib
export PYTHONUNBUFFERED=TRUE
export ENGINE_DB_HOST='localhost'

echo -e "\nActivating virtual environment"
source $WORKING_DIRECTORY/venv/bin/activate
source $WORKING_DIRECTORY/.env
export ENGINE_DB_PASS=$LOCAL_ENGINE_DB_PASS

# Add the ais folder with our __init__.py so we can import it as a python module
export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"

echo "Starting NG911 address points report..."a
#send_teams "Starting NG911 address points report."
python $WORKING_DIRECTORY/ais/engine/bin/output_address_points_for_ng911.py

echo "Running make_reports.py.."
python $WORKING_DIRECTORY/ais/engine/bin/make_reports.py

echo "Starting updating EPAM address points report."
python $WORKING_DIRECTORY/ais/engine/bin/update_address_points.py

echo "Engine reports have completed."
