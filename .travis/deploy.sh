#!/usr/bin/env bash

set -e

# 1. Create a virtual environment
echo "Creating a virtual environment"
.travis/init_environment.sh
source env/bin/activate

# 2. Install the awsebcli
echo "Installing AWS Elastic Beanstalk CLI"
pip install awsebcli

# 3. Configure eb
echo "Installing configuration for eb tool"
mkdir -p ~/.aws
cat > ~/.aws/credentials <<EOF
[phila]
aws_secret_access_key = $AWS_SECRET
aws_access_key_id = $AWS_ID
EOF

# 4. Determine whether the current branch is configured for an environment
echo "Checking for environment corresponding to current branch"
source scripts/eb_env_utils.sh
get_test_env EB_ENV EB_BLUEGREEN_STATUS || {
  echo "Could not find a production or swap environment" ;
  exit 1 ;
}

# 5. Push the current branch
echo "Pushing code to $EB_BLUEGREEN_STATUS environment $EB_ENV"
git checkout "$TRAVIS_BRANCH"
eb deploy $EB_ENV

if [ "$EB_BLUEGREEN_STATUS" = "Swap" ] ; then
  EB_NEW_PROD_ENV=$EB_ENV
  EB_OLD_PROD_ENV=$(.travis/get_prod_env.sh) || {
    echo "Could not find a production environment to swap with" ;
    exit 1 ;
  }

  echo "Setting deployment environment variables"
  # Start as background processes in parallel
  eb setenv $EB_OLD_PROD_ENV EB_BLUEGREEN_STATUS=Staging &
  eb setenv $EB_NEW_PROD_ENV EB_BLUEGREEN_STATUS=Production &
  # Wait for both
  wait $(jobs -p)

  echo "Swapping out $EB_OLD_PROD_ENV for $EB_NEW_PROD_ENV"
  eb swap --destination_name $EB_OLD_PROD_ENV $EB_NEW_PROD_ENV

  #
  # NOTE: SNAPSHOT AND TERMINATE OLD PRODUCTION ENVIRONMENT NOW.
  #
fi
