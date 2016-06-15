#!/usr/bin/env bash

set -e

# Install all the project dependencies.
echo 'Installing project dependencies'
sudo apt-get update
sudo apt-get install build-essential libaio1 -y
sudo apt-get install libpq-dev libgeos-dev -y
sudo apt-get install python-virtualenv unzip nginx -y
