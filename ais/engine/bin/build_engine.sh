#!/usr/bin/env bash

echo "Activating virtual environment"
source ../../../env/bin/activate

echo "Running the engine"

echo "Loading Streets"
ais engine run load_streets

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Street Aliases"
ais engine run load_street_aliases

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Making Intersections"
ais engine run make_street_intersections

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading OPA Properties"
ais engine run load_opa_properties

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading DOR parcels"
ais engine run load_dor_parcels

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading DOR condos"
ais engine run load_dor_condos

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading PWD Parcels"
ais engine run load_pwd_parcels


if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Curbs"
ais engine run load_curbs

if [ $? -ne 0 ]
then
  echo "Loading table failed. Exiting."
  exit 1;
fi

echo "Loading Addresses"
ais engine run load_addresses

if [ $? -ne 0 ]
then
  echo "Loading addresses failed. Exiting."
  exit 1;
fi

echo "Geocoding Addresses"
ais engine run geocode_addresses

if [ $? -ne 0 ]
then
  echo "Geocoding addresses failed. Exiting."
  exit 1;
fi

echo "Making Address Tags from Linked Addresses"
ais engine run make_linked_tags

if [ $? -ne 0 ]
then
  echo "Making address tags failed. Exiting."
  exit 1;
fi

echo "Geocoding addresses from links"
ais engine run geocode_addresses_from_links

if [ $? -ne 0 ]
then
  echo "Geocoding addresses from links failed. Exiting."
  exit 1;
fi

echo "Making Address Summary"
ais engine run make_address_summary

if [ $? -ne 0 ]
then
  echo "Making address summary failed. Exiting."
  exit 1;
fi

echo "Loading Service Areas"
ais engine run load_service_areas

if [ $? -ne 0 ]
then
  echo "Loading service areas failed. Exiting."
  exit 1;
fi

echo "Making Service Area Summary"
ais engine run make_service_area_summary

if [ $? -ne 0 ]
then
  echo "Making service area summary failed. Exiting."
  exit 1;
fi
