
REM UPDATE_DB SCRIPT FOR VM PROD MACHINE (RUNNING WINDOWS 2008 SERVER)

set SCRIPT_DIR=cd

REM ------------------------------------------------------------------

REM Get staging/swap environment name and db_uri

set pout=powershell "..\..\..\bin\update_db_utilities.ps1"
set /A i=0
@echo off &setlocal enabledelayedexpansion
for /f "delims=" %%G in ('%pout%') do ( ^
	set /A i+=1
	IF !i! == 1 set EB_ENV=%%G
	IF !i! == 2 set ENV_STATUS_NAME=%%G
 	IF !i! == 3 set DB_URI=%%G )

REM -------------------------------

REM Build Engine (DOS)
REM FOR NOW MANUALLY CALL SCRIPT "BUILD_ENGINE" FROM CMD

REM ----------------------------------

REM Run engine tests (DOS)

REM FOR NOW MANUALLY CALL SCRIPT "TEST_ENGINE" FROM CMD

REM ADD CONDITION FOR TESTS TO PASS TO CONTINUE

REM ----------------------------------

REM Copy the engine database (DOS)

echo "Copying the engine database"

del /f /s /q D:\temp 1>nul
rmdir /s /q D:\temp
mkdir D:\temp
set db_dump_file_loc=D:\temp\ais_engine.dump
pg_dump -Fc -U ais_engine -n public ais_engine > %db_dump_file_loc%

REM ------------------------------------------------------------------

REM Restore Database (DOS)

echo "Restoring the engine DB into the %EB_ENV% environment "

psql -U ais_engine -h %DB_URI% -d ais_engine -c "DROP SCHEMA IF EXISTS public CASCADE;"
psql -U ais_engine -h %DB_URI% -d ais_engine -c "CREATE SCHEMA public;"
psql -U ais_engine -h %DB_URI% -d ais_engine -c "GRANT ALL ON SCHEMA public TO postgres;"
psql -U ais_engine -h %DB_URI% -d ais_engine -c "GRANT ALL ON SCHEMA public TO public;"
psql -U ais_engine -h %DB_URI% -d ais_engine -c "CREATE EXTENSION postgis;"
REM psql -U ais_engine -h %DB_URI% -d ais_engine -c "CREATE EXTENSION pgtrgm;"
pg_restore -h %DB_URI% -d ais_engine -U ais_engine -c %db_dump_file_loc%

REM------------------------------------------------------------------

REM Swap & Deploy (DOS/POWERSHELL)

echo "Marking the %EB_ENV% environment as ready for testing (swap)"
eb setenv -e %EB_ENV% EB_BLUEGREEN_STATUS=Swap


REM ---- PLEASE FINISH ROUTINE MANUALLY BY RESTARTING LAST BUILD IN AIS REPO ON TRAVIS -----

REM ----THE REMAINING PART IS NOT FUNCTIONAL - NEED TO CONFIG PROD VM FOR TRAVIS-----

REM Get last travis build and parse build number
set lb=travis history --branch master --limit 1

REM set LAST_BUILD=$lb.split(' ')[0].split('#')[1] # this is powershell > 2.0 syntax (5.0)
REM $e = ($lb -split(' '))[0]
REM $LAST_BUILD = ($e -split('#'))[1]

REM echo "Restarting the latest master branch build (requires travis CLI)"
REM travis restart $LAST_BUILD

# NOTE: Travis-CI will take over from here. Check in the .travis/deploy script
# for further step.