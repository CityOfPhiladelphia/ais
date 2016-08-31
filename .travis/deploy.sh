#!/usr/bin/env bash

set -e

# 1. Create a virtual environment
echo "Creating a virtual environment"
virtualenv env -p python3
source env/bin/activate

# 2. Install the awsebcli
echo "Installing AWS Elastic Beanstalk CLI"
pip install awsebcli

# 3. Configure eb
echo "Installing configuration for eb tool"
mkdir -p ~/.aws
cat > ~/.aws/credentials <<EOF
[eb-cli]
aws_secret_access_key = $AWS_ID
aws_access_key_id = $AWS_SECRET
EOF

# 4. Determine whether the current branch is configured for an environment
echo "Checking for environment corresponding to current branch"
if test ! eb list | grep "*"
then
  # 4a. If not, exit with 0.
  echo "No environment configured for branch \"$TRAVIS_BRANCH\""
  exit 0
fi

# 5. Push the current branch
echo "Pushing code to environment"
eb push
