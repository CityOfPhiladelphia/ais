#!/usr/bin/env bash

datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

error_file="build_errors_"
out_file="build_log_"
error_file_loc=../log/$error_file$datestamp.txt
out_file_loc=../log/$out_file$datestamp.txt

mkdir -p ../log

bash build_engine.sh > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)

end_dt=$(date +%Y%m%d%T)

echo "Time Summary: "
echo "Started: "$start_dt
echo "Finished: "$end_dt






