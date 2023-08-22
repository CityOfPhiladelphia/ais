#!/usr/bin/env bash

WORKING_DIRECTORY=/home/ubuntu/ais
cd $WORKING_DIRECTORY

export ORACLE_HOME=/usr/lib/oracle/18.5/client64
export PATH=$PATH:$ORACLE_HOME/bin
export LD_LIBRARY_PATH=$ORACLE_HOME/lib
export PYTHONUNBUFFERED=TRUE
echo -e "\nActivating virtual environment"
source $WORKING_DIRECTORY/venv/bin/activate
# Add the ais folder with our __init__.py so we can import it as a python module
export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"

echo "Running make_reports.py.."
python $WORKING_DIRECTORY/ais/engine/bin/make_reports.py
