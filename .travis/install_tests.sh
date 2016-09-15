#!/usr/bin/env bash

set -e

# 1. Create a virtual environment
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
.travis/get_test_env.sh EB_ENV EB_BLUEGREEN_STATUS || {
  echo "Could not find a production or swap environment" ;
  exit 1 ;
}

# 5. Download the environment variables
echo "Downloading environment for branch \"$TRAVIS_BRANCH\""
eb printenv $EB_ENV | tail -n +2 > .env

# Install the application dependencies
.travis/install_app.sh
