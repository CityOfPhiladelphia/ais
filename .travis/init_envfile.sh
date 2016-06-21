#!/usr/bin/env bash

set -ex

PROJECT_NAME=$1
TRAVIS_BRANCH=$2

source env/bin/activate
if aws s3 ls s3://phila-deploy/${PROJECT_NAME}/ | grep '.env.${TRAVIS_BRANCH}$' ; then
  aws s3 cp s3://phila-deploy/${PROJECT_NAME}/.env.${TRAVIS_BRANCH} .env
else
  aws s3 cp s3://phila-deploy/${PROJECT_NAME}/.env .env
fi
echo "" >> .env  # Add a blank line, just in case
echo "PROJECT_NAME=$PROJECT_NAME" >> .env
deactivate
