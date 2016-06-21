#!/usr/bin/env bash

set -e

AWS_ID=$1
AWS_SECRET=$2

if test ! -f ~/.aws/config ; then
    source env/bin/activate
    pip install awscli
    deactivate

    echo 'Configuring AWS CLI'
    mkdir -p ~/.aws
    cat > ~/.aws/config <<EOF
[default]
aws_access_key_id = $AWS_ID
aws_secret_access_key = $AWS_SECRET
output = text
region = us-east-1
EOF
fi
