set SCRIPT_DIR=cd

rem Get start time:

for /F "tokens=1-4 delims=:.," %%a in ("%time%") do (
   set /A "start=(((%%a*60)+1%%b %% 100)*60+1%%c %% 100)*100+1%%d %% 100"
)

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
echo %hh%:%mm%:%ss%