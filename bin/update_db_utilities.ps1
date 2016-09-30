# Getting Staging Environment

# Find the environment that is either marked as staging or ready to swap in.

$EB_ENVS = eb list
#$EB_ENV
#$ENV_STATUS_NAME
#$env_vars
#$DB_URI

for($i=0; $i -lt $EB_ENVS.Length; $i+=1){

   $env_vars = eb printenv $EB_ENVS[$i]
   $staging = $env_vars -like '*Staging*'
   $swap = $env_vars -like '*Swap*'

   if($staging.length -gt 0){
       $EB_ENV=$EB_ENVS[$i]
       $ENV_STATUS_NAME="Staging"
       }
   ElseIf($swap.length -gt 0){
       $EB_ENV=$EB_ENVS[$i]
       $ENV_STATUS_NAME="Swap"
       }
}

# get staging/swap DB_URI
#echo "Obtaining the staging/swap database uri"
$vars = eb printenv $EB_ENV
$b=$vars -like '*SQLALCHEMY_DATABASE_URI*'
# $DB_URI=$b.split('@')[1].split(':')[0] # this is powershell > 2.0 syntax (5.0)
$c=($b -split '@')[1]
$DB_URI=($c -split ':')[0]

#echo out for use in batch script
$EB_ENV, $ENV_STATUS_NAME, $DB_URI 

