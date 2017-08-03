#!/usr/bin/env bash

start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt

error_file="build_errors_"
out_file="build_log_"
error_file_loc=../log/$error_file$dt.txt
out_file_loc=../log/$out_file$dt.txt

mkdir -p ../log

(bash build_engine.sh 1>&2) 2> >(tee $out_file_loc) > >(tee $error_file_loc)

end_dt=$(date +%Y%m%d%T)

echo "Time Summary: "
echo "Started: "$start_dt
echo "Finished: "$end_dt