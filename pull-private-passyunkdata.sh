#!/bin/bash
source ./config-secrets.sh
# These are really noisy and we don't want that right now
aws s3 cp s3://ais-static-files/election_block.csv ./docker-build-files/ --only-show-errors
aws s3 cp s3://ais-static-files/usps_zip4s.csv ./docker-build-files/ --only-show-errors
