#!/usr/bin/env bash

SCRIPTS_DIR=$(dirname $0)/../scripts

$SCRIPTS_DIR/init_awscli.sh
$SCRIPTS_DIR/init_envfile.sh

pip install honcho jinja2
honcho run $SCRIPTS_DIR/install.sh

pip install pytest
