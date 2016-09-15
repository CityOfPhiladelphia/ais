#!/usr/bin/env bash

ENVS=$(eb list)

__ENV_VAR_NAME=$1
__ENV_STATUS_NAME=$2

# Find the environment that is marked to swap in.
for env in $ENVS ; do
  eb printenv $env | grep --quiet "EB_BLUEGREEN_STATUS = Swap"
  if [ $? -eq 0 ] ; then
    eval "export $__ENV_VAR_NAME=$env"
    eval "export $__ENV_STATUS_NAME=Swap"
    exit 0
  fi
done

# If none is marked to swap, then use the environment marked as production.
for env in $ENVS ; do
  eb printenv $env | grep --quiet "EB_BLUEGREEN_STATUS = Production"
  if [ $? -eq 0 ] ; then
    eval "export $__ENV_VAR_NAME=$env"
    eval "export $__ENV_STATUS_NAME=Production"
    exit 0
  fi
done

# If no environment is found, exit with an error.
exit 1
