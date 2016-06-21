#!/usr/bin/env bash

set -e

source env/bin/activate
if ! aws help &>/dev/null ; then
    pip install awscli
fi

echo 'Configuring AWS CLI'
mkdir -p ~/.aws
cat > ~/.aws/config <<EOF
[default]
aws_access_key_id = $AWS_ID
aws_secret_access_key = $AWS_SECRET
output = text
region = us-east-1
EOF
deactivate
