#!/usr/bin/env bash

set -e

# Set up the virtual environment
.travis/init_environment.sh

# Set up AWS access
.travis/init_awscli.sh '$AWS_ID' '$AWS_SECRET'

# Transfer the .env file to the server
.travis/init_envfile.sh $PROJECT_NAME $TRAVIS_BRANCH

# Install the application dependencies
.travis/install_app.sh
