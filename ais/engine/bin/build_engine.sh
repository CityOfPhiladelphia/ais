#!/usr/bin/env bash

WORKING_DIRECTORY=/home/ubuntu/ais
cd $WORKING_DIRECTORY

export ORACLE_HOME=/usr/lib/oracle/18.5/client64
export PATH=$PATH:$ORACLE_HOME/bin
export LD_LIBRARY_PATH=$ORACLE_HOME/lib
export PYTHONUNBUFFERED=TRUE
echo "Setting DEV_TEST to true so we use the local database."
export DEV_TEST="true"
echo -e "\nActivating virtual environment"
source $WORKING_DIRECTORY/venv/bin/activate
# Add the ais folder with our __init__.py so we can import it as a python module
export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"

source $WORKING_DIRECTORY/.env

export ENGINE_DB_HOST="localhost"
export ENGINE_DB_PASS=$LOCAL_ENGINE_DB_PASS

echo "Running the engine build!"

SCRIPTS=(
  "load_streets" 
  "load_street_aliases" 
  "make_street_intersections"
  "load_opa_properties"
  "load_ng911_address_points"
  "load_dor_parcels"
  "load_dor_condos"
  "load_pwd_parcels"
  "load_curbs"
  "load_addresses"
  "geocode_addresses"
  "make_linked_tags"
  "geocode_addresses_from_links"
  "make_address_summary"
  "load_service_areas"
  "make_service_area_summary"
)

run_script() {
  echo ""
  echo "********************************************************************************"
  echo "Running script '$1'"
  ais engine --script "$1"
  if [[ $? -ne 0 ]]
  then
    echo "Loading table failed. Exiting."
    exit 1;
  fi
}

for script in "${SCRIPTS[@]}"; do
  run_script $script
done
