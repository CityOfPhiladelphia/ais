# Getting Staging Environment

# Find the environment that is either marked as staging or ready to swap in.

$EB_ENVS = eb list
#$EB_ENV
#$ENV_STATUS_NAME
#$env_vars
#$DB_URI

for($i=0; $i -lt $EB_ENVS.Length; $i+=1){

   $env_vars = eb status $EB_ENVS[$i]
   $staging = $env_vars -like '*staging*'
   $production = $env_vars -like '*prod*'

   if($staging.length -gt 0){
       $EB_ENV=$EB_ENVS[$i]
       $ENV_STATUS_NAME="Staging"
       }
}

# get staging/swap DB_URI
#echo "Obtaining the staging/swap database uri"
$vars = eb printenv $EB_ENV
$b=$vars -like '*SQLALCHEMY_DATABASE_URI*'
# $DB_URI=$b.split('@')[1].split(':')[0] # this is powershell > 2.0 syntax (5.0)
$c=($b -split '@')[1]
$DB_URI=($c -split ':')[0]
# get staging/swap EB_BLUEGREEN_STATUS property
#echo "Obtaining the staging/swap env property"
$vars = eb printenv $EB_ENV
$b=$vars -like '*EB_BLUEGREEN_STATUS*'
$ENV_STATUS_NAME=($b -split '= ')[1]
$EB_ENV
$DB_URI
$ENV_STATUS_NAME


#echo out for use in batch script
#$EB_ENV, $ENV_STATUS_NAME, $DB_URI

