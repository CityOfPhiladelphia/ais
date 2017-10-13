#!/usr/bin/env bash

postgis_dsn=$1
oracle_dsn_gis_ais=$2

# ADDRESS_SUMMARY
psql -U ais_engine -h localhost -d ais_engine -c "ALTER TABLE address_summary add COLUMN objectid serial;"
psql -U ais_engine -h localhost -d ais_engine -c "alter table address_summary add column shape geometry(Point,2272);"
psql -U ais_engine -h localhost -d ais_engine -c "update address_summary set shape = st_setsrid(st_makepoint(geocode_x, geocode_y), 2272);"
the_el read address_summary --connection-string $postgis_dsn --output-file address_summary.csv --geometry-support postgis --from-srid 2272 --to-srid 2272
python remove_special_characters.py "address_summary.csv" "address_summary_cleaned.csv"
the_el describe_table address_summary --connection-string $postgis_dsn --output-file address_summary_schema.json --geometry-support postgis
###the_el create_table temp_address_summary --connection-string $oracle_dsn_gis_ais address_summary_schema.json --geometry-support sde --db-schema GIS_AIS
python create_table_from_schema.py "address_summary"
the_el write t_address_summary --connection-string $oracle_dsn_gis_ais --table-schema-path address_summary_schema.json --geometry-support sde --input-file address_summary_cleaned.csv --skip-headers
the_el swap_table t_address_summary address_summary --connection-string $oracle_dsn_gis_ais
psql -U ais_engine -h localhost -d ais_engine -c "ALTER TABLE address_summary DROP COLUMN objectid;"
psql -U ais_engine -h localhost -d ais_engine -c "ALTER TABLE address_summary DROP COLUMN shape;"

#DOR_PARCEL_ADDRESS_COMP_ANALYSIS
the_el read dor_parcel_address_analysis --connection-string $postgis_dsn --output-file dor_parcel_address_analysis.csv --geometry-support postgis
the_el describe_table dor_parcel_address_analysis --connection-string $postgis_dsn --output-file dor_parcel_address_analysis_schema.json --geometry-support postgis
#the_el create_table TEMP_DOR_PARCEL_ADDRESS_COMP_ANALYSIS --connection-string $oracle_dsn_gis_dor dor_parcel_address_comp_analysis_schema.json --geometry-support sde --db-schema GIS_DOR
python create_table_from_schema.py "dor_parcel_address_analysis"
the_el write t_dor_parcel_address_analysis --connection-string $oracle_dsn_gis_ais --table-schema-path dor_parcel_address_analysis_schema.json --geometry-support sde --input-file dor_parcel_address_analysis.csv --skip-headers
the_el swap_table t_dor_parcel_address_analysis dor_parcel_address_analysis --connection-string $oracle_dsn_gis_ais
