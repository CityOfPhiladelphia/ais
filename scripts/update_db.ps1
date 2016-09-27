
$SCRIPT_DIR = pwd
echo $SCRIPT_DIR

# Build Engine

echo "Activating virtual environment"
cd ../env/scripts
./activate.bat
cd $SCRIPT_DIR

echo "Running the engine"
# # python build_engine.py

# Run pg_dump
echo "Dumping the engine DB"
# # pg_dump -Fc -U ais_engine -n public ais_engine > ais_engine.dump

# Get Staging Environment

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
$db_uri=$b.split('@')[1].split(':')[0]
$db_uri

# NOTE: SPIN UP STAGING/SWAP INSTANCE NOW.

# Restore Database
echo "Restoring the engine DB into the $EB_ENV environment "
# # pg_restore -h $db_uri -d ais_engine -U ais_engine -c ais_engine.dump
#pg_restore -d ais_engine_test -U ais_engine -c ais_engine.dump

# Swap & Deploy
echo "Marking the $EB_ENV environment as ready for testing (swap)"
# # eb setenv -e $ENV_VAR_NAME EB_BLUEGREEN_STATUS=Swap

echo "Restarting the latest master branch build (requires travis CLI)"
# Learn how to do this in powershell
##if ! hash travis ; then
##  echo "This step requires the Travis-CI CLI. To install and configure, see:
##  https://github.com/travis-ci/travis.rb#installation"
##  exit 1
##fi

# Get last travis build and parse build number
$lb = travis history --branch master --limit 1
$LAST_BUILD = $l.split(' ')[0].split('#')[1]
# # travis restart $LAST_BUILD

# NOTE: Travis-CI will take over from here. Check in the .travis/deploy script
# for further step.

