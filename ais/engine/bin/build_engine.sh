#!/usr/bin/env bash

WORKING_DIRECTORY=/home/ubuntu/ais

echo "Activating virtual environment"
source $WORKING_DIRECTORY/venv/bin/activate
# Add the ais folder with our __init__.py so we can import it as a python module
export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
#source ../../../env/bin/activate

echo "Running the engine"

echo "Loading Streets"
ais engine --script load_streets

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Street Aliases"
ais engine --script load_street_aliases

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Making Intersections"
ais engine --script make_street_intersections

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading OPA Properties"
ais engine --script load_opa_properties

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading DOR parcels"
ais engine --script load_dor_parcels

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading DOR condos"
ais engine --script load_dor_condos

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading PWD Parcels"
ais engine --script load_pwd_parcels


if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Curbs"
ais engine --script load_curbs

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
ais engine --script get_pwd_matches_from_manual_opa_geocodes
if [ $? -ne 0 ]
then
  echo "Adding manual opa-pwd parcel matches failed. Exiting."
  exit 1;
fi

echo "Geocoding Addresses"
ais engine --script geocode_addresses

if [ $? -ne 0 ]
then
  echo "Geocoding addresses failed. Exiting."
  exit 1;
fi

echo "Making Address Tags from Linked Addresses"
ais engine --script make_linked_tags

if [ $? -ne 0 ]
then
  echo "Making address tags failed. Exiting."
  exit 1;
fi

echo "Geocoding addresses from links"
ais engine --script geocode_addresses_from_links

if [ $? -ne 0 ]
then
  echo "Geocoding addresses from links failed. Exiting."
  exit 1;
fi

echo "Making Address Summary"
ais engine --script make_address_summary

if [ $? -ne 0 ]
then
  echo "Making address summary failed. Exiting."
  exit 1;
fi

echo "Loading Service Areas"
ais engine --script load_service_areas

if [ $? -ne 0 ]
then
  echo "Loading service areas failed. Exiting."
  exit 1;
fi

echo "Making Service Area Summary"
ais engine --script make_service_area_summary

if [ $? -ne 0 ]
then
  echo "Making service area summary failed. Exiting."
  exit 1;
fi
