#!/usr/bin/env bash

PROJECT_NAME=$1
TRAVIS_BRANCH=$2

source env/bin/activate
aws s3 cp s3://phila-deploy/${PROJECT_NAME}/.env.${TRAVIS_BRANCH} .env
echo "" >> .env  # Add a blank line, just in case
echo "PROJECT_NAME=$PROJECT_NAME" >> .env
deactivate