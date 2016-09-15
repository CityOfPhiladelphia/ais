#!/usr/bin/env bash

ENVS=$(eb list)

# Find the environment that is either marked as staging or ready to swap in.
for env in $ENVS ; do
  vars=$(eb printenv $env)

  echo "$vars" | grep --quiet "EB_BLUEGREEN_STATUS = Staging"
  if [ $? -eq 0 ] ; then
    echo $env
    exit 0
  fi

  echo $vars | grep --quiet "EB_BLUEGREEN_STATUS = Swap"
  if [ $? -eq 0 ] ; then
    echo $env
    exit 0
  fi
done

# If no environment is found, exit with an error.
exit 1
