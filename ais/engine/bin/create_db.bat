@echo off

rem config
set ENGINE_DB=ais_engine
set ENGINE_USER=ais_engine

rem set a few vars
set PGUSER=postgres
set PGPASSWORD=%POSTGRES_PASSWORD%

rem create engine user and start using it
psql -c "create role %ENGINE_USER% with superuser login password '%ENGINE_PASSWORD%';"

rem create database
psql -c "create database %ENGINE_DB% with owner %ENGINE_USER%;"

rem create extensions
set PGUSER=%ENGINE_USER%
set PGPASSWORD=%ENGINE_PASSWORD%
psql -c "create extension postgis;create extension adminpack;create extension pg_trgm;"

rem allow internal connections to the db
echo host    ais_engine       ais_engine     0.0.0.0/0               md5 >> %PGDATA%\pg_hba.conf
pg_ctl reload
