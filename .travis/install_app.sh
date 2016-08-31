#!/usr/bin/env bash

set -e


# Install python requirements on python3 with library paths
echo 'Installing other application Python requirements'
pip install --requirement requirements.app.txt


# Run any management commands for migration, static files, etc.
