#!/usr/bin/env bash

set -e

source env/bin/activate
pip install pytest
py.test ais
