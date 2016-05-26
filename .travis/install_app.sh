#!/usr/bin/env bash

set -e
SCRIPT_DIR=$(dirname $0)
BASE_DIR=$(dirname $SCRIPT_DIR)
VENDOR_PATH=/srv/$PROJECT_NAME/vendor



# Load utilities
. $SCRIPT_DIR/utils.sh



# Install all the project dependencies.
echo 'Installing project dependencies'
sudo apt-get update
sudo apt-get install python-pip build-essential libaio1 alien -y
sudo apt-get install libpq-dev libgeos-dev -y
sudo apt-get install python3-dev python3-pip unzip nginx -y


# Download, install, and configure Oracle Instant Client. Note that the EC2
# instance must have been created with a role that can read objects from S3.
#
# https://oracle-base.com/articles/misc/oracle-instant-client-installation
if test ! -d $VENDOR_PATH/oracle ; then
    echo 'Downloading and installing Oracle Instant Client'
    sudo mkdir -p $VENDOR_PATH/oracle
    sudo chown `whoami`:`whoami` $VENDOR_PATH/oracle
    if test ! -f $VENDOR_PATH/oracle/oracle-instantclient12.1-basiclite-12.1.0.2.0-1.x86_64.rpm ; then
        aws s3 cp s3://ais-deploy/oracle-instantclient12.1-basiclite-12.1.0.2.0-1.x86_64.rpm $VENDOR_PATH/oracle
    fi
    if test ! -f $VENDOR_PATH/oracle/oracle-instantclient12.1-devel-12.1.0.2.0-1.x86_64.rpm ; then
        aws s3 cp s3://ais-deploy/oracle-instantclient12.1-devel-12.1.0.2.0-1.x86_64.rpm $VENDOR_PATH/oracle
    fi
    if [ "$(dpkg -l | grep "ii  oracle")" = "" ] ; then
        sudo alien --install $VENDOR_PATH/oracle/oracle-instantclient12.1*rpm
    fi
fi

# Install python requirements on python3 with library paths
echo 'Installing other application Python requirements'
sudo pip3 install --requirement requirements.txt

# Download the zip4 file for passyunk and place it wherever passyunk was installed
$SCRIPT_DIR/update_zip4.sh


# Run any management commands for migration, static files, etc.

