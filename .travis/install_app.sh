#!/usr/bin/env bash

set -e
SCRIPT_DIR=$(dirname $0)
BASE_DIR=$(dirname $SCRIPT_DIR)
VENDOR_PATH=$BASE_DIR/vendor



# Load utilities
. $SCRIPT_DIR/utils.sh

# Download, install, and configure Oracle Instant Client. Note that the EC2
# instance must have been created with a role that can read objects from S3.
#
# https://oracle-base.com/articles/misc/oracle-instant-client-installation
if test ! -d $VENDOR_PATH/oracle ; then
    echo 'Downloading and installing Oracle Instant Client'
    mkdir -p $VENDOR_PATH/oracle
    if test ! -f $VENDOR_PATH/oracle/instantclient-basiclite-linux.x64-12.1.0.2.0.zip ; then
        aws s3 cp s3://ais-deploy/instantclient-basiclite-linux.x64-12.1.0.2.0.zip $VENDOR_PATH/oracle
    fi
    if test ! -f $VENDOR_PATH/oracle/instantclient-sdk-linux.x64-12.1.0.2.0.zip ; then
        aws s3 cp s3://ais-deploy/instantclient-sdk-linux.x64-12.1.0.2.0.zip $VENDOR_PATH/oracle
    fi
    if [ "$(dpkg -l | grep "ii  oracle")" = "" ] ; then
        unzip $VENDOR_PATH/oralce/instantclient*.zip
        sudo alien --install $VENDOR_PATH/oracle/oracle-instantclient12.1*rpm
    fi
fi


# Install python requirements on python3 with library paths
echo 'Installing other application Python requirements'
source env/bin/activate
pip install --requirement requirements.txt
deactivate

# Download the zip4 file for passyunk and place it wherever passyunk was installed
$SCRIPT_DIR/update_zip4.sh


# Run any management commands for migration, static files, etc.

