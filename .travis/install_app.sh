#!/usr/bin/env bash

set -e


# Install python requirements on python3 with library paths
echo 'Installing other application Python requirements'
pip3 install --requirement requirements.app.txt

# Create empty config.py
echo 'Initializing the configuration'
mkdir -p instance
touch instance/config.py


# Run any management commands for migration, static files, etc.
