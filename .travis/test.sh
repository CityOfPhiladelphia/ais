#!/usr/bin/env bash

set -e

source env/bin/activate
pip install pytest honcho --force-reinstall

honcho run pytest ais -s --ignore=ais/engine/tests

