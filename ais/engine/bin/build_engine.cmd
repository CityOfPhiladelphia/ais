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
REM ais engine run load_streets

echo. && echo "Loading Street Aliases"
REM ais engine run load_street_aliases

echo. && echo "Loading OPA Properties"
REM ais engine run load_opa_properties

echo. && echo "Loading DOR parcels"
REM ais engine run load_dor_parcels

echo. && echo "Loading PWD Parcels"
REM ais engine run load_pwd_parcels

echo. && echo "Loading Curbs"
REM ais engine run load_curbs

echo. && echo "Loading Addresses"
REM ais engine run load_addresses

echo. && echo "Loading Zip Ranges"
REM ais engine run load_zip_ranges

echo. && echo "Geocoding Addresses"
REM ais engine run geocode_addresses

echo. && echo "Making Address Summary"
REM ais engine run make_address_summary

echo. && echo "Loading Service Areas"
REM ais engine run load_service_areas

echo. && echo "Making Service Area Summary"
REM ais engine run make_service_area_summary


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
