#!/usr/bin/env bash

set -e

source env/bin/activate
pip install pytest honcho --force-reinstall
sudo apt install nmap
nmap -p 5432 $rds_market_dsn
honcho run pytest ais -s --ignore=ais/engine/tests
