#!/usr/bin/env bash

echo 'Installing Zip4 data for address parsing'

source env/bin/activate

# Find the folder where the Passyunk package is installed
PASSYUNK_SCRIPT="import passyunk; from os.path import dirname; print(dirname(passyunk.__file__))"
PASSYUNK_DIR=$(python -c "$PASSYUNK_SCRIPT")

# Download and place the zip4 data
mkdir -p $PASSYUNK_DIR/pdata
aws s3 cp s3://ais-deploy/uspszip4.csv $PASSYUNK_DIR/pdata

deactivate