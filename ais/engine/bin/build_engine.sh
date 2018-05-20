#!/usr/bin/env bash

echo "Activating virtual environment"
source ../../../env/bin/activate

echo "Running the engine"

echo "Loading Streets"
ais engine run load_streets

echo "Loading Street Aliases"
ais engine run load_street_aliases

echo "Making Intersections"
ais engine run make_street_intersections

echo "Loading OPA Properties"
ais engine run load_opa_properties

echo "Loading DOR Parcels"
ais engine run load_dor_parcels

echo "Loading DOR Condos"
ais engine run load_dor_condos

echo "Loading PWD Parcels"
ais engine run load_pwd_parcels

echo "Loading NG911 Address Points"
ais engine run load_ng911_address_points

echo "Loading Curbs"
ais engine run load_curbs

echo "Loading Addresses"
ais engine run load_addresses

echo "Geocoding Addresses"
ais engine run geocode_addresses

echo "Making Address Tags from Linked Addresses"
ais engine run make_linked_tags

echo "Geocoding addresses from links"
ais engine run geocode_addresses_from_links

echo "Making Address Summary"
ais engine run make_address_summary

echo "Loading Service Areas"
ais engine run load_service_areas

echo "Making Service Area Summary"
ais engine run make_service_area_summary
