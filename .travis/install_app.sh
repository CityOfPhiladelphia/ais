#!/usr/bin/env bash

set -e
SCRIPT_DIR=$(dirname $0)
BASE_DIR=$(dirname $SCRIPT_DIR)
VENDOR_PATH=`pwd`/$BASE_DIR/vendor



# Load utilities
. $SCRIPT_DIR/utils.sh

# Download, install, and configure Oracle Instant Client. Note that the EC2
# instance must have been created with a role that can read objects from S3.
#
# https://oracle-base.com/articles/misc/oracle-instant-client-installation
echo 'Downloading and installing Oracle Instant Client'
source env/bin/activate
mkdir -p $VENDOR_PATH/oracle

# Download the insall zips
if test ! -f $VENDOR_PATH/oracle/instantclient-basiclite-linux.x64-12.1.0.2.0.zip ; then
    aws s3 cp s3://ais-deploy/instantclient-basiclite-linux.x64-12.1.0.2.0.zip $VENDOR_PATH/oracle
fi
if test ! -f $VENDOR_PATH/oracle/instantclient-sdk-linux.x64-12.1.0.2.0.zip ; then
    aws s3 cp s3://ais-deploy/instantclient-sdk-linux.x64-12.1.0.2.0.zip $VENDOR_PATH/oracle
fi

# Unzip into the vendor path
if test ! -d $VENDOR_PATH/oracle/instantclient_12_1 ; then
    cd $VENDOR_PATH/oracle
    unzip "instantclient*.zip"
    cd ../..
fi

# Create a soft link to the linkable library if it does not exist
if test ! -f $VENDOR_PATH/oracle/instantclient_12_1/libclntsh.so ; then
    ln -s libclntsh.so.12.1 $VENDOR_PATH/oracle/instantclient_12_1/libclntsh.so
fi

# Add the vendored library path to the environment file
if ! grep "^LD_LIBRARY_PATH" $BASE_DIR/.env ; then
    echo "LD_LIBRARY_PATH=$VENDOR_PATH/oracle/instantclient_12_1" >> $BASE_DIR/.env
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$VENDOR_PATH/oracle/instantclient_12_1
fi
if ! grep "^ORACLE_HOME" $BASE_DIR/.env ; then
    echo "ORACLE_HOME=$VENDOR_PATH/oracle/instantclient_12_1" >> $BASE_DIR/.env
    export ORACLE_HOME=$VENDOR_PATH/oracle/instantclient_12_1
fi
deactivate

# Install python requirements on python3 with library paths
echo 'Installing other application Python requirements'
source env/bin/activate
pip install --requirement requirements.txt
deactivate

# Download the zip4 file for passyunk and place it wherever passyunk was installed
$SCRIPT_DIR/update_zip4.sh


# Run any management commands for migration, static files, etc.
