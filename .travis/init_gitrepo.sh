#!/usr/bin/env bash

PROJECT_NAME=$1
TRAVIS_BRANCH=$2
TRAVIS_REPO_SLUG=$3

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
