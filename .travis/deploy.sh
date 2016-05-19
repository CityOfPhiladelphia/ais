#!/usr/bin/env bash

set -e

KEYFILE=deploy.pem
INSTANCE_USER=ubuntu
ENCRYPTION_KEY='encrypted_${ENCRYPTION_ID}_key'
ENCRYPTION_IV='encrypted_${ENCRYPTION_ID}_iv'

# Install the AWS CLI if it's not already
if test ! -f ~/.aws/config ; then
    pip install awscli

    echo 'Configuring AWS CLI'
    mkdir -p ~/.aws
    cat > ~/.aws/config <<EOF
[default]
aws_access_key_id = $AWS_ID
aws_secret_access_key = $AWS_SECRET
output = text
region = us-east-1
EOF
fi

echo 'Retrieving machine IP from AWS'
PROJECT_NAME=$(python -c "print('$TRAVIS_REPO_SLUG'.split('/')[1])")
INSTANCE_IP=`aws ec2 describe-instances --filters \
  "Name=instance-state-name,Values=running" \
  "Name=tag:Branch,Values=$TRAVIS_BRANCH" \
  "Name=tag:Project,Values=$PROJECT_NAME" | \
  grep '^INSTANCES' | cut -f14`
if [ -z "$INSTANCE_IP" ]; then echo "No machine found for branch \"$TRAVIS_BRANCH\". Skipping deploy" && exit 0; fi
ssh-keyscan -H $INSTANCE_IP | sudo tee --append /etc/ssh/ssh_known_hosts > /dev/null

# Copy the SSH Key
echo 'Decrypting and installing the SSH private key'
aws s3 cp s3://phila-deploy/${PROJECT_NAME}/deploy.pem.enc.$TRAVIS_BRANCH deploy.pem.enc
# *************************************
# PASTE TRAVIS DECRYPTION COMMAND BELOW
# *************************************
openssl aes-256-cbc -K \$${ENCRYPTION_KEY} -iv \$${ENCRYPTION_IV} -in deploy.pem.enc -out ~/.ssh/${KEYFILE} -d
chmod 600 ~/.ssh/deploy.pem
eval $(ssh-agent -s)
ssh-add ~/.ssh/deploy.pem

# SSH onto the machine, install git if it's not already installed, and
# download the latest version of the code.
echo 'Ensuring that git is installed'
ssh -i $KEYFILE ${INSTANCE_USER}@${INSTANCE_IP} '

    # Install git
    if [ "$(sudo dpkg -l | grep "ii  git")" = "" ] ; then
        sudo apt-get update
        sudo apt-get install git -y
    fi

    # Clone or pull the latest code
    if test -d $PROJECT_NAME ; then
        cd $PROJECT_NAME
        git fetch
        git checkout $TRAVIS_BRANCH
        git pull
    else
        git clone https://github.com/${TRAVIS_REPO_SLUG}.git
        cd $PROJECT_NAME
        git checkout $TRAVIS_BRANCH
    fi

'

# Set up your environment file
echo 'Setting up environment variables'
ssh -i $KEYFILE ${INSTANCE_USER}@${INSTANCE_IP} '

    cd $PROJECT_NAME
    aws s3 cp s3://phila-deploy/${PROJECT_NAME}/.env.${TRAVIS_BRANCH} .env
    echo "" >> .env  # Add a blank line, just in case
    echo "PROJECT_NAME=$PROJECT_NAME" >> .env

'

# Run the install script on the server to complete the setup process.
echo 'Starting the install script'
ssh -i $KEYFILE ${INSTANCE_USER}@${INSTANCE_IP} '
    
    # Install pip
    if [ "$(sudo dpkg -l | grep "ii  python-pip")" = "" ] ; then
        sudo apt-get update
        sudo apt-get install python-pip -y
    fi

    sudo pip install honcho jinja2

    cd ais
    honcho run scripts/install.sh

'