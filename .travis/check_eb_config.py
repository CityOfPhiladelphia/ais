#!/usr/bin/env python

import os, sys, yaml

# Get the travis branch from the environment
branch = os.environ.get('TRAVIS_BRANCH', '')

# Load the eb configuration
with open('.elasticbeanstalk/config.yml') as cfgfile:
    cfg = yaml.load(cfgfile)

# If the branch is not configured, exit with an error code
branchcfg = cfg.get('branch-defaults', {}).get(branch)
if branchcfg is None:
    sys.exit(1)

print(branchcfg['environment'])
