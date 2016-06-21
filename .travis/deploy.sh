#!/usr/bin/env bash

set -e

SCRIPTS_DIR=$(dirname $0)
KEYFILE=${DEPLOY_KEYFILE:-"~/.ssh/deploy.pem"}
INSTANCE_USER=ubuntu
ENCRYPTION_KEY='encrypted_${ENCRYPTION_ID}_key'
ENCRYPTION_IV='encrypted_${ENCRYPTION_ID}_iv'
INSTALL_SSH=0

for i in "$@" ; do
  case $i in
    -s|--install-ssh)
      INSTALL_SSH=1
      shift # past argument=value
      ;;
    -k=*|--keyfile=*)
      KEYFILE="${i#*=}"
      shift # past argument=value
      ;;
    *)
            # unknown option
    ;;
  esac
done


# Install the AWS CLI if it's not already
$SCRIPTS_DIR/init_awscli.sh $AWS_ID $AWS_SECRET

echo 'Retrieving machine IP from AWS'
PROJECT_NAME=$(python -c "print('$TRAVIS_REPO_SLUG'.split('/')[1])")
INSTANCE_IP=`aws ec2 describe-instances --filters \
  "Name=instance-state-name,Values=running" \
  "Name=tag:Branch,Values=$TRAVIS_BRANCH" \
  "Name=tag:Project,Values=$PROJECT_NAME" | \
  grep '^INSTANCES' | cut -f14`
if [ -z "$INSTANCE_IP" ]; then echo "No machine found for branch \"$TRAVIS_BRANCH\". Skipping deploy" && exit 0; fi

# *************************************
# Set up SSH
#
# 1. Get the fingerprint of the EC2 instance and install it into the known
#    hosts.
# 2. Download and install a private key that the remote machine knows about.
#
# These steps will only run if you specify the -s|--install-ssh flag

if [ $INSTALL_SSH == 1 ] ; then
  # Copy the SSH Key. Use a branch-specific key if available. Otherwise, use a
  # project-general one.
  #
  # NOTE: The following assumes that you have uploaded the encrypted SSH key
  #       for the project to the S3 deployment bucket. If you have not, see
  #       https://docs.travis-ci.com/user/encrypting-files/ for instructions on
  #       encrypting files with Travis.

  echo 'Decrypting and installing the SSH private key'
  if aws s3 ls s3://phila-deploy/${PROJECT_NAME}/ | grep 'deploy.pem.enc.${TRAVIS_BRANCH}$' ; then
    aws s3 cp s3://phila-deploy/${PROJECT_NAME}/deploy.pem.enc.${TRAVIS_BRANCH} deploy.pem.enc
  else
    aws s3 cp s3://phila-deploy/${PROJECT_NAME}/deploy.pem.enc deploy.pem.enc
  fi
  openssl aes-256-cbc -K \$${ENCRYPTION_KEY} -iv \$${ENCRYPTION_IV} -in deploy.pem.enc -out $KEYFILE -d
  chmod 600 $KEYFILE
  eval $(ssh-agent -s)
  ssh-add $KEYFILE

  echo 'Installing machine''s IP into known hosts'
  INSTANCE_FINGERPRINT=`ssh-keyscan -H $INSTANCE_IP`
  if [ "$(grep '$INSTANCE_FINGERPRINT' ~/.ssh/known_hosts)" == "" ] ; then
    echo "$INSTANCE_FINGERPRINT" >> ~/.ssh/known_hosts 2> /dev/null
  fi
fi

# *************************************

# SSH onto the machine, install git if it's not already installed, and
# download the latest version of the code. Set up the environment file and run
# the install script on the server to complete the setup process.
ssh -i $KEYFILE ${INSTANCE_USER}@${INSTANCE_IP} "
    echo 'Ensuring that git is installed'
    if ! hash git &>/dev/null ; then
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

    echo 'Installing system packages'
    .travis/init_system.sh

    echo 'Creating the virtual environment'
    .travis/init_environment.sh

    echo 'Activating the virtual environment'
    source env/bin/activate
    pip install honcho jinja2

    echo 'Setting up AWS access'
    .travis/init_awscli.sh '$AWS_ID' '$AWS_SECRET'

    echo 'Setting up environment variables'
    .travis/init_envfile.sh '$PROJECT_NAME' '$TRAVIS_BRANCH'

    echo 'Starting the install script'
    honcho run .travis/install_app.sh
    honcho run .travis/install_server.sh
    echo 'Deploy has completed; app should be available at:'
    echo 'http://$INSTANCE_IP/'
    deactivate
"
