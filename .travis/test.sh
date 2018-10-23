#!/usr/bin/env bash

set -e

source env/bin/activate
pip install pytest honcho --force-reinstall
sudo apt install nmap
nmap -p 5432 $rds_market_dsn -Pn
#telnet $rds_market_dsn 5432
PGPASSWORD=$pgpassword psql -U ais_engine -d ais_engine -h $rds_market_dsn -c "select count(*) from address_summary;"
honcho run pytest ais -s --ignore=ais/engine/tests
