#!/usr/bin/env bash

echo 'Installing Zip4 data for address parsing'
PASSYUNK_SCRIPT="import passyunk; from os.path import dirname; print(dirname(passyunk.__file__))"
PASSYUNK_DIR=$(python3 -c "$PASSYUNK_SCRIPT")
sudo chown `whoami`:`whoami` $PASSYUNK_DIR
mkdir -p $PASSYUNK_DIR/pdata
aws s3 cp s3://ais-deploy/uspszip4.csv $PASSYUNK_DIR/pdata
