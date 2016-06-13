#!/usr/bin/env bash

set -e

# Set up the virtual environment
.travis/init_environment.sh

# Set up AWS access
.travis/init_awscli.sh

# Transfer the .env file to the server
.travis/init_envfile.sh $PROJECT_NAME $TRAVIS_BRANCH
