set SCRIPT_DIR=cd

rem Get start time:

for /F "tokens=1-4 delims=:.," %%a in ("%time%") do (
   set /A "start=(((%%a*60)+1%%b %% 100)*60+1%%c %% 100)*100+1%%d %% 100"
)

echo "Activating virtual environment"

cd ../../../env/scripts
call activate.bat

echo. && echo "Running the engine"

echo. && echo "Loading Streets"
ais engine run load_streets

echo. && echo "Loading Street Aliases"
ais engine run load_street_aliases

echo. && echo "Making Intersections"
ais engine run make_street_intersections

echo. && echo "Loading OPA Properties"
ais engine run load_opa_properties

echo. && echo "Loading DOR parcels"
ais engine run load_dor_parcels

echo. && echo "Loading PWD Parcels"
ais engine run load_pwd_parcels

echo. && echo "Loading Curbs"
ais engine run load_curbs

echo. && echo "Loading Addresses"
ais engine run load_addresses

echo. && echo "Making Address Tags from Linked Addresses"
ais engine run make_linked_tags

echo. && echo "Geocoding Addresses"
ais engine run geocode_addresses

echo. && echo "Geocoding Addresses from Links"
ais engine run geocode_addresses_from_links

echo. && echo "Making Address Summary"
ais engine run make_address_summary

echo. && echo "Loading Service Areas"
ais engine run load_service_areas

echo. && echo "Making Service Area Summary"
ais engine run make_service_area_summary


rem Get end time:

for /F "tokens=1-4 delims=:.," %%a in ("%time%") do (
   set /A "end=(((%%a*60)+1%%b %% 100)*60+1%%c %% 100)*100+1%%d %% 100"
)

rem Get elapsed time:

set /A elapsed=end-start

rem Show elapsed time:

set /A hh=elapsed/(60*60*100), rest=elapsed%%(60*60*100), mm=rest/(60*100), rest%%=60*100, ss=rest/100, cc=rest%%100
if %mm% lss 10 set mm=0%mm%
if %ss% lss 10 set ss=0%ss%
if %cc% lss 10 set cc=0%cc%

echo. && echo "Time elapsed: %hh%:%mm%:%ss%"
