#!/usr/bin/env bash

set -e

# Make sure Python 3.6 is installed
if ! python3.6 -V &>/dev/null ; then
  echo 'Install Python 3.6'
  sudo add-apt-repository ppa:fkrull/deadsnakes
  sudo apt-get update
  sudo apt-get install -y python3.6 python3.6-dev
  sudo apt-get install -y iproute2
fi

echo 'Create a virutal environment'
virtualenv env -p python3.6 || echo 'Virtual environment already created.'

echo 'Writing Travis instance IP info:'
ip a
curl ipinfo.io/ip
