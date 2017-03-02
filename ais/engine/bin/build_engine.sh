#!/usr/bin/env bash
dt=$(date +%Y%m%d)
error_file="build_errors_"
out_file="build_log_"
error_file_loc=../log/$error_file$dt.txt
out_file_loc=../log/$out_file$dt.txt
mkdir -p $error_file_loc
mkdir -p $out_file_loc
command 2>> $error_file_loc 1>> $out_file_loc

echo "Running the engine"

echo "Loading Streets"
ais engine run load_streets

echo "Loading Street Aliases"
ais engine run load_street_aliases

echo "Making Intersections"
ais engine run make_street_intersections

echo "Loading OPA Properties"
ais engine run load_opa_properties

echo "Loading DOR parcels"
ais engine run load_dor_parcels

echo "Loading PWD Parcels"
ais engine run load_pwd_parcels

echo "Loading Curbs"
ais engine run load_curbs

echo "Loading Addresses"
ais engine run load_addresses

echo "Making Address Tags from Linked Addresses"
ais engine run make_linked_tags

echo "Geocoding Addresses"
ais engine run geocode_addresses

echo "Making Address Summary"
ais engine run make_address_summary

echo "Loading Service Areas"
ais engine run load_service_areas

echo "Making Service Area Summary"
ais engine run make_service_area_summary