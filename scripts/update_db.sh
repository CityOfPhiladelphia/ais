#!/usr/bin/env bash

set -e

SCRIPT_DIR=$(dirname "$0")

echo "Running the engine [TODO]"
# TODO

echo "Dumping the engine DB [TODO]"
# TODO pg_dump ...

echo "Finding the staging environment"
source $SCRIPT_DIR/eb_env_utils.sh
get_staging_env EB_ENV EB_BLUEGREEN_STATUS || {
  echo "Could not find an environment marked staging or swap" ;
  exit 1 ;
}

#
# NOTE: SPIN UP STAGING/SWAP INSTANCE NOW.
#

echo "Restoring the engine DB onto the staging environment [TODO]"
# TODO pg_restore ...

echo "Marking the staging environment as ready for testing (swap)"
eb setenv -e $EB_ENV EB_BLUEGREEN_STATUS=Swap

echo "Restarting the latest master branch build (requires travis CLI)"
if ! hash travis ; then
  echo "This step requires the Travis-CI CLI. To install and configure, see:
  https://github.com/travis-ci/travis.rb#installation"
  exit 1
fi
LAST_BUILD=$(travis history --branch master --limit 1 | cut --fields=1 --delimiter=" ")
# The build number has a number sign as the first character. We need to strip
# it off.
LAST_BUILD=${LAST_BUILD:1}
travis restart $LAST_BUILD

# NOTE: Travis-CI will take over from here. Check in the .travis/deploy script
# for further step.