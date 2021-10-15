#!/bin/bash
source ./config-secrets.sh
aws s3 cp s3://ais-static-files/election_block.csv .
aws s3 cp s3://ais-static-files/usps_zip4s.csv .
