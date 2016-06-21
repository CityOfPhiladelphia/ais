#!/usr/bin/env bash

set -e
SCRIPT_DIR=$(dirname $0)
BASE_DIR=$(dirname $SCRIPT_DIR)



# Load utilities
. $SCRIPT_DIR/utils.sh


# Install the deployment requirements
echo 'Installing deployment Python requirements'
source env/bin/activate
pip install --requirement requirements.server.txt
deactivate


# Set up the web server
echo 'Setting up the web server configuration'
sudo honcho export upstart /etc/init \
    --app $PROJECT_NAME \
    --user nobody \
    --procfile $BASE_DIR/Procfile

sudo sed -e "s/exec gunicorn/source env\/bin\/activate ; exec gunicorn/" -i /etc/init/ais-web-1.conf

# Set up nginx
# https://docs.getsentry.com/on-premise/server/installation/#proxying-with-nginx
echo 'Generating an nginx configuration'
echo "$(generate_nginx_config_nossl)" | sudo tee /etc/nginx/sites-available/$PROJECT_NAME
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -fs /etc/nginx/sites-available/$PROJECT_NAME /etc/nginx/sites-enabled/$PROJECT_NAME

# Re/start the web server
echo 'Restarting the web server'
sudo service $PROJECT_NAME restart
sudo service nginx reload
