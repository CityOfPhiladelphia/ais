#!/usr/bin/env bash

set -e

# 1. Create a virtual environment
echo "Creating a virtual environment"
.travis/init_environment.sh
source env/bin/activate

# 2. Install the awsebcli
echo "Installing AWS Elastic Beanstalk CLI"
# pip install awsebcli
# new version isn't working - install older version:
pip install awsebcli==3.8.8 --force-reinstall
# 3. Configure eb
echo "Installing configuration for eb tool"
eb_version=eb --version
echo "AWSEBCLI Version: "$eb_version
mkdir -p ~/.aws
cat > ~/.aws/credentials <<EOF
[phila]
aws_secret_access_key = $AWS_SECRET
aws_access_key_id = $AWS_ID
EOF
cat > ~/.aws/config <<EOF
[profile eb-cli]
aws_secret_access_key = $AWS_SECRET
aws_access_key_id = $AWS_ID
EOF

if [ $TRAVIS_BRANCH = "develop" ] || [ $TRAVIS_BRANCH = "develop_test" ]; then
    eb deploy ais-api-develop
    exit 0
fi

# 4. Determine whether the current branch is configured for an environment
echo "Checking for environment corresponding to current branch"
echo $TRAVIS_BRANCH
source bin/eb_env_utils.sh
echo $EB_ENVS
get_test_env EB_ENV EB_BLUEGREEN_STATUS || {
  echo "Could not find a production or swap environment" ;
  exit 1 ;
}

# 5. Push the current branch
echo "Pushing code to $EB_BLUEGREEN_STATUS environment $EB_ENV"
git checkout "$TRAVIS_BRANCH"

avoid_timeout & eb deploy $EB_ENV --timeout 30

if [ "$EB_BLUEGREEN_STATUS" = "Swap" ] ; then
  EB_NEW_PROD_ENV=$EB_ENV
  EB_OLD_PROD_ENV=$(get_prod_env) || {
    echo "Could not find a production environment to swap with" ;
    exit 1 ;
  }

  echo "Setting deployment environment variables"
  # Start as background processes in parallel
  eb setenv --environment $EB_OLD_PROD_ENV SWAP=False --timeout 30 &
  eb setenv --environment $EB_NEW_PROD_ENV SWAP=False --timeout 30 #&
  # Wait for both
#  wait $(jobs -p)

  echo "Swapping out $EB_OLD_PROD_ENV for $EB_NEW_PROD_ENV"
  eb swap --destination_name $EB_OLD_PROD_ENV $EB_NEW_PROD_ENV

  #
  # NOTE: SNAPSHOT AND TERMINATE OLD PRODUCTION ENVIRONMENT NOW.
  #
fi

exit $?
