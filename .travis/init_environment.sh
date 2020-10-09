#!/usr/bin/env bash

set -e

# Make sure Python 3.6 is installed
if ! python3.6 -V &>/dev/null ; then
  echo 'Install Python 3.6'
  # install this repo to get python3.6 pip, which is not aviailable under default ubuntu 16.04
  sudo apt-get update
  sudo add-apt-repository ppa:jonathonf/python-3.6 
  sudo add-apt-repository ppa:deadsnakes/ppa

  sudo apt install python3.6 python3.6-dev python3.6-venv

  # Then get manual pip installation script
  wget https://bootstrap.pypa.io/get-pip.py
  sudo python3.6 get-pip.py

  sudo ln -s /usr/bin/python3.6 /usr/local/bin/python3
  sudo ln -s /usr/local/bin/pip /usr/local/bin/pip3

#  sudo add-apt-repository ppa:fkrull/deadsnakes
  #sudo apt-get install -y python3.6 python3.6-dev
  sudo apt-get install -y iproute2
fi

echo 'Create a virutal environment'
virtualenv env -p python3.6 || echo 'Virtual environment already created.'

echo 'Writing Travis instance IP info:'
ip a
curl ipinfo.io/ip
