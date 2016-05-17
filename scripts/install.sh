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
sudo pip install awscli

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

if test ! -f $VENDOR_PATH/oracle/instantclient_12_1/libclntsh.so ; then
    ln -s libclntsh.so.12.1 $VENDOR_PATH/oracle/instantclient_12_1/libclntsh.so
fi

if test ! -f ; then
    ln -s instantclient_12_1 $VENDOR_PATH/oracle/lib
fi

# if [ "$(grep "oracle/instantclient_12_1" ~/.bashrc)" = "" ] ; then
#     echo 'Installing Oracle Instant Client to load on bash start'
#     cat >> ~/.bashrc <<____EOF
#     export LD_LIBRARY_PATH=$VENDOR_PATH/oracle/instantclient_12_1:\$LD_LIBRARY_PATH
#     export PATH=\$PATH:$VENDOR_PATH/oracle/instantclient_12_1
#     export ORACLE_HOME=$VENDOR_PATH/oracle
# ____EOF
#     source ~/.bashrc
# fi

# Download and install the private key for installing passyunk
echo 'Downloading and installing private key for GitHub'
if ! test -f /etc/ssh/github ; then
    aws s3 cp s3://ais-deploy/github ~/.ssh
    sudo bash <<EOF
        mv ~/.ssh/github /etc/ssh/
        chmod 600 /etc/ssh/github
EOF
fi

# Load the GitHub private key and install passyunk
echo 'Installing Passyunk from a private repository'
sudo bash <<EOF
    eval `ssh-agent -s`
    ssh-add /etc/ssh/github
    ssh-keyscan -H github.com | sudo tee /etc/ssh/ssh_known_hosts

    pip3 install -e git+ssh://github.com/CityOfPhiladelphia/passyunk.git#egg=passyunk
EOF

# Install python requirements on python3 with library paths
echo 'Installing other application Python requirements'
sudo pip3 install --requirement requirements.txt


# # Configure the AWS CLI
# echo 'Configuring AWS CLI'
# mkdir -p ~/.aws
# cat > ~/.aws/config <<EOF
# [default]
# aws_access_key_id = $AWS_ID
# aws_secret_access_key = $AWS_SECRET
# output = text
# region = us-east-1
# EOF




# Run any management commands for migration, static files, etc.



# Set up the web server
echo 'Setting up the web server configuration'
sudo honcho export upstart /etc/init \
    --app $PROJECT_NAME \
    --user nobody \
    --procfile $BASE_DIR/Procfile

# Set up nginx
# https://docs.getsentry.com/on-premise/server/installation/#proxying-with-nginx
echo 'Generating an nginx configuration'
echo "$(generate_nginx_conf_nossl)" | sudo tee /etc/nginx/sites-available/$PROJECT_NAME
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -fs /etc/nginx/sites-available/$PROJECT_NAME /etc/nginx/sites-enabled/$PROJECT_NAME

# Re/start the web server
echo 'Restarting the web server'
sudo service $PROJECT_NAME restart
sudo service nginx reload
