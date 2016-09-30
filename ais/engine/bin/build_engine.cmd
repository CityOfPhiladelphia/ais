REM Build Engine

set SCRIPT_DIR=cd

echo "Activating virtual environment"

cd ../../../env/scripts
call activate.bat

echo "Running the engine"

ais engine run load_streets
ais engine run load_street_aliases
ais engine run load_opa_properties
ais engine run load_dor_parcels
ais engine run load_pwd_parcels
ais engine run load_curbs
ais engine run load_addresses
ais engine run load_zip_ranges
ais engine run geocode_addresses
ais engine run make_address_summary
ais engine run load_service_areas
ais engine run make_service_area_summary
