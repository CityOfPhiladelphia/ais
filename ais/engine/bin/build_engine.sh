#!/usr/bin/env bash

WORKING_DIRECTORY=/home/ubuntu/ais

export ORACLE_HOME=/usr/lib/oracle/18.5/client64
export PATH=$PATH:$ORACLE_HOME/bin
export LD_LIBRARY_PATH=$ORACLE_HOME/lib

echo "Activating virtual environment"
source $WORKING_DIRECTORY/venv/bin/activate
# Add the ais folder with our __init__.py so we can import it as a python module
export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
#source ../../../env/bin/activate

echo "Running the engine"

echo "Loading Streets" 
ais engine --script load_streets # Runtime 0:00:52

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Street Aliases"
ais engine --script load_street_aliases # Runtime 0:00:01

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Making Intersections"
ais engine --script make_street_intersections # Runtime 0:02:12

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading OPA Properties"
ais engine --script load_opa_properties # Runtime 0:06:05

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading DOR parcels"
ais engine --script load_dor_parcels # Runtime 0:13:27

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading DOR condos"
ais engine --script load_dor_condos # Runtime 0:01:53

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading PWD Parcels"
ais engine --script load_pwd_parcels # Runtime 0:12:50


if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Curbs"
ais engine --script load_curbs # Runtime 0:02:07

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Addresses"
ais engine --script load_addresses

if [ $? -ne 0 ]
then
  echo "Loading addresses failed. Exiting."
  exit 1;
fi

echo "Loading opa active accounts and matching pwd parcels for properties without pwd parcel match"
ais engine --script get_pwd_matches_from_manual_opa_geocodes # Runtime unknown

if [ $? -ne 0 ]
then
  echo "Adding manual opa-pwd parcel matches failed. Exiting."
  exit 1;
fi

echo "Geocoding Addresses"
ais engine --script geocode_addresses # Runtime: 0:01:20

if [ $? -ne 0 ]
then
  echo "Geocoding addresses failed. Exiting."
  exit 1;
fi

echo "Making Address Tags from Linked Addresses"
ais engine --script make_linked_tags # Runtime: 0:01:11

if [ $? -ne 0 ]
then
  echo "Making address tags failed. Exiting."
  exit 1;
fi

echo "Geocoding addresses from links"
ais engine --script geocode_addresses_from_links # Runtime: 0:00:01

if [ $? -ne 0 ]
then
  echo "Geocoding addresses from links failed. Exiting."
  exit 1;
fi

echo "Making Address Summary"
ais engine --script make_address_summary # Runtime: 0:02:05

if [ $? -ne 0 ]
then
  echo "Making address summary failed. Exiting."
  exit 1;
fi

echo "Loading Service Areas"
ais engine --script load_service_areas # Runtime: 0:02:18

if [ $? -ne 0 ]
then
  echo "Loading service areas failed. Exiting."
  exit 1;
fi

echo "Making Service Area Summary"
ais engine --script make_service_area_summary # Runtime: 0:00:01

if [ $? -ne 0 ]
then
  echo "Making service area summary failed. Exiting."
  exit 1;
fi
