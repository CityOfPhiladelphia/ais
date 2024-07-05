#!/usr/bin/env bash
set -e 

postgis_dsn=$1
oracle_dsn_gis_ais=$2
source ../../../env/bin/activate
source ../../../bin/eb_env_utils.sh

# ADDRESS_SUMMARY
echo "updating address_summary"
echo "adding spatial columns"
psql -U ais_engine -h localhost -d ais_engine << EOF
ALTER TABLE address_summary_transformed ADD COLUMN objectid serial;
ALTER TABLE address_summary_transformed ADD COLUMN shape geometry(Point,2272);
UPDATE address_summary_transformed SET shape = st_setsrid(st_makepoint(geocode_x, geocode_y), 2272);
EOF
echo "reading address_summary"
the_el read address_summary_transformed --connection-string $postgis_dsn --output-file address_summary.csv --geometry-support postgis
echo "cleaning address_summary"
python remove_special_characters.py "address_summary.csv" "address_summary_cleaned.csv"
echo "describing address_summary"
the_el describe_table address_summary_transformed --connection-string $postgis_dsn --output-file address_summary_schema.json --geometry-support postgis
python remove_schema_constraints.py "address_summary_schema.json"
echo "creating temp table"
python create_table_from_schema.py "address_summary"
echo "writing to temp table"
the_el write t_address_summary --connection-string $oracle_dsn_gis_ais --table-schema-path address_summary_schema.json --geometry-support sde --from-srid 2272 --input-file address_summary_cleaned.csv --skip-headers
if [ $? -ne 0 ]
then
  echo "Writing to temp address_summary table failed. Exiting."
  psql -U ais_engine -h localhost -d ais_engine -c "ALTER TABLE address_summary_transformed DROP COLUMN objectid;"
  psql -U ais_engine -h localhost -d ais_engine -c "ALTER TABLE address_summary_transformed DROP COLUMN shape;"
  send_slack "Writing to temp address_summary table failed. Exiting."
  exit 1;
fi
echo "Swapping table"
the_el swap_table t_address_summary address_summary --connection-string $oracle_dsn_gis_ais
if [ $? -ne 0 ]
then
  echo "Address summary table swap failed."
  send_slack "Address summary swap failed."
  psql -U ais_engine -h localhost -d ais_engine -c "DROP TABLE address_summary_transformed;"
  exit 1;
fi
echo "Completed updating address summary in DataBridge."
send_slack "Completed updating address summary in DataBridge."

echo "Cleaning up."
psql -U ais_engine -h localhost -d ais_engine -c "DROP TABLE address_summary_transformed;"


