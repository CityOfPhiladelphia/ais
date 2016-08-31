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
[eb-cli]
aws_secret_access_key = $AWS_ID
aws_access_key_id = $AWS_SECRET
EOF

# 4. Determine whether the current branch is configured for an environment
echo "Checking for environment corresponding to current branch"
if .travis/check_eb_config.py
then
  # 4a. If so, download the environment variables
  echo "Downloading environment for branch \"$TRAVIS_BRANCH\""
  eb printenv > .env
fi

# Install the application dependencies
.travis/install_app.sh
