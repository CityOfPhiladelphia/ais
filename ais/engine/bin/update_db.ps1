
$SCRIPT_DIR = pwd
echo $SCRIPT_DIR

# Build Engine

echo "Activating virtual environment"
cd ../../../env/scripts
./activate

#echo "Running the engine"

#ais engine run load_streets
#ais engine run load_street_aliases
#ais engine run load_opa_properties
#ais engine run load_dor_parcels
#ais engine run load_pwd_parcels
#ais engine run load_curbs
#ais engine run load_addresses
#ais engine run load_zip_ranges
#ais engine run geocode_addresses
#ais engine run make_address_summary
#ais engine run load_service_areas
#ais engine run make_service_area_summary

echo "Running engine tests"
#pytest ../../ais/engine

# Dumping the engine
$db_dump_file_loc = $env:temp + "\ais_engine.dump"
echo "Dumping the engine DB"
$db_dump_file_loc
pg_dump -Fc -U ais_engine -n public ais_engine > $db_dump_file_loc

# Getting Staging Environment

# Find the environment that is either marked as staging or ready to swap in.

$EB_ENV = eb list
$ENV_VAR_NAME
$ENV_STATUS_NAME
$env_vars
$db_uri

for($i=0; $i -lt $EB_ENV.Length; $i+=1){

   $env_vars = eb printenv $EB_ENV[$i]
   $staging = $env_vars -like '*Staging*'
   $swap = $env_vars -like '*Swap*'

   if($staging.length -gt 0){
       $ENV_VAR_NAME=$EB_ENV[$i]
       $ENV_STATUS_NAME="Staging"
       }
   ElseIf($swap.length -gt 0){
       $ENV_VAR_NAME=$EB_ENV[$i]
       $ENV_STATUS_NAME="Swap"
       }
}

echo $ENV_VAR_NAME;
echo $ENV_STATUS_NAME;

# get staging/swap db_uri
echo "Obtaining the staging/swap database uri"
$vars = eb printenv $ENV_VAR_NAME
$b=$vars -like '*SQLALCHEMY_DATABASE_URI*'
# $db_uri=$b.split('@')[1].split(':')[0] # this is powershell > 2.0 syntax (5.0)
$c=($b -split '@')[1]
$db_uri=($c -split ':')[0]
$db_uri

# NOTE: SPIN UP STAGING/SWAP INSTANCE NOW.

# Restore Database
echo "Restoring the engine DB into the $EB_ENV environment "
pg_restore -h $db_uri -d ais_engine -U ais_engine -c db_dump_file_loc

# Swap & Deploy
echo "Marking the $EB_ENV environment as ready for testing (swap)"
eb setenv -e $ENV_VAR_NAME EB_BLUEGREEN_STATUS=Swap

echo "Restarting the latest master branch build (requires travis CLI)"
# Translate to powershell
##if ! hash travis ; then
##  echo "This step requires the Travis-CI CLI. To install and configure, see:
##  https://github.com/travis-ci/travis.rb#installation"
##  exit 1
##fi

# Get last travis build and parse build number
$lb = travis history --branch master --limit 1
#$LAST_BUILD = $lb.split(' ')[0].split('#')[1] # this is powershell > 2.0 syntax (5.0)
$LAST_BUILD = ((($lb -split(' '))[0]) -split('#'))[1]
travis restart $LAST_BUILD

# NOTE: Travis-CI will take over from here. Check in the .travis/deploy script
# for further step.

