#!/usr/bin/env bash

set -e

# Make sure Python 3.5 is installed
if ! python3.5 -V &>/dev/null ; then
  echo 'Install Python 3.5'
  sudo add-apt-repository ppa:fkrull/deadsnakes
  sudo apt-get update
  sudo apt-get install -y python3.5 python3.5-dev
fi

echo 'Create a virutal environment'
virtualenv env -p python3.5 || echo 'Virtual environment already created.'
