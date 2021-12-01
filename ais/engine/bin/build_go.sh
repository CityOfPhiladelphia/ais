#!/usr/bin/env bash
# V2 worked on by Roland

# exit when any command fails
set -e

WORKING_DIRECTORY=/root/ais
cd $WORKING_DIRECTORY
echo "Working directory is $WORKING_DIRECTORY"

# Has our send_teams and get_prod_env functions
source $WORKING_DIRECTORY/ais/engine/bin/ais-utils.sh

trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# echo an error message before exiting
trap 'echo "\"${last_command}\" command exited with code $?."' EXIT


datestamp=$(date +%Y%m%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt


activate_venv_source_libaries() {
    if [ ! -d $WORKING_DIRECTORY/env ]; then
        echo "Activating/creating venv.."
        python3.6 -m venv $WORKING_DIRECTORY/env 
        source $WORKING_DIRECTORY/env/bin/activate
        # Add the ais folder with our __init__.py so we can import it as a python module
        export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
	# used for python3.5, not needed with the pip version that's installed under 3.6
        # Looks like pip 18.1 works and is what we want.
        #pip install --upgrade "pip < 21.0"
        pip install wheel
	# used for python3.5
        #python setup.py bdist_wheel 
        pip install -r $WORKING_DIRECTORY/requirements.txt
        # Install AIS as a python module, needed in tests.
        python setup.py develop
    else
        echo "Activating virtual environment"
        source $WORKING_DIRECTORY/env/bin/activate
        # Add the ais folder with our __init__.py so we can import it as a python module
        export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
    fi
}


pull_repo() {
    echo "Ensuring necessary repos are updated from github"
    # GET LATEST CODE FROM GIT REPO
    git fetch origin && git pull
    cd $WORKING_DIRECTORY/env/src/passyunk
    git fetch origin && git pull
    cd $WORKING_DIRECTORY
}


# CREATE ENGINE LOG FILES
setup_log_files() {
    echo "Setting up log files"
    mkdir -p $WORKING_DIRECTORY/ais/engine/log
    error_file="build_errors_"
    out_file="build_log_"
    error_file_loc=$WORKING_DIRECTORY/ais/engine/log/$error_file$datestamp.txt
    out_file_loc=$WORKING_DIRECTORY/ais/engine/log/$out_file$datestamp.txt
}


# Check for and load credentials
# Note: Make sure to have your ais/instance/config.py populated
# This wil be needed for the engine build to pull in data.
# config-secrets.sh contains AWS 
check_load_creds() {
    echo "Loading credentials and passwords into the environment"
    . $WORKING_DIRECTORY/pull-private-passyunkdata.sh
    cp $WORKING_DIRECTORY/docker-build-files/election_block.csv $WORKING_DIRECTORY/env/src/passyunk/passyunk/pdata/
    cp $WORKING_DIRECTORY/docker-build-files/usps_zip4s.csv $WORKING_DIRECTORY/env/src/passyunk/passyunk/pdata/

    file $WORKING_DIRECTORY/instance/config.py
    file $WORKING_DIRECTORY/config-secrets.sh
    source $WORKING_DIRECTORY/config-secrets.sh
}


# RUN BUILD ENGINE
# Note: you need to have your ais/instance/config.py populated
# with database connection info for this to work!
# See check_load_creds function.
build_engine() {
    echo "Starting new engine build"
    send_teams "Starting new engine build."
    bash $WORKING_DIRECTORY/ais/engine/bin/build_engine.sh > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
    send_teams "Engine build has completed."
    end_dt=$(date +%Y%m%d%T)
    echo "Time Summary: "
    echo "Started: "$start_dt
    echo "Finished: "$end_dt
}


# Get AWS production environment
identify_prod() {
    echo "Finding the production environment via CNAME"
    prod_color=$(get_prod_env || {
      echo "Could not find the production environment" ;
      exit 1 ;
    })
    echo "Production environment is: $prod_color"
    if [[ "$prod_color" == "blue" ]]; then
        staging_color="green" 
        staging_db_uri=$GREEN_ENGINE_CNAME
        staging_lb_uri=$GREEN_CNAME

        prod_db_uri=$BLUE_ENGINE_CNAME
        prod_lb_uri=$BLUE_CNAME
    else
        staging_color="blue"
        staging_db_uri=$BLUE_ENGINE_CNAME
        staging_lb_uri=$BLUE_CNAME

        prod_db_uri=$GREEN_ENGINE_CNAME
        prod_lb_uri=$GREEN_CNAME
    fi
    staging_tg_arn=$(aws elbv2 describe-target-groups | grep "${staging_color}-tg" | grep TargetGroupArn| cut -d"\"" -f4)
    prod_tg_arn=$(aws elbv2 describe-target-groups | grep "${prod_color}-tg" | grep TargetGroupArn| cut -d"\"" -f4)
}


# Run tests, uses PGPASSWORD env var to access it.
engine_tests() {
    echo "Running engine tests against locally built database."
    cd $WORKING_DIRECTORY
    #send_teams "Running tests."
    pytest $WORKING_DIRECTORY/ais/engine/tests/test_engine.py
    if [ $? -ne 0 ]
    then
      echo "Engine tests failed"
      send_teams "Engine tests have failed."
      exit 1;
    fi
    send_teams "Engine tests have passed."
}


api_tests() {
    echo "Running API tests....."
    cd $WORKING_DIRECTORY
    pytest $WORKING_DIRECTORY/ais/api/tests/
    if [ $? -ne 0 ]
    then
      echo "API tests failed"
      send_teams "API tests failed."
      exit 1;
    fi
    send_teams "API tests passed."
}


# Make a copy (Dump) the newly built local engine db
dump_local_db() {
    echo "Dumping the newly built engine database.."
    sent_teams "Dumping the newly built engine database.."
    mkdir -p $WORKING_DIRECTORY/ais/engine/backup
    db_dump_file_loc=$WORKING_DIRECTORY/ais/engine/backup/ais_engine.dump
    #pg_dump -Fc -U ais_engine -n public ais_engine > $db_dump_file_loc
    if [ $? -ne 0 ]
    then
      echo "DB dump failed"
      exit 1;
    fi
}


# Update (Restore) AWS RDS instance to staging database
restore_db_to_staging() {
    echo "Restoring the engine DB to $staging_db_uri"
    send_teams "Restoring the engine DB to $staging_db_uri"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "DROP SCHEMA IF EXISTS public CASCADE;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "CREATE SCHEMA public;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO postgres;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO public;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "CREATE EXTENSION postgis;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "CREATE EXTENSION pg_trgm;"
    pg_restore -h $staging_db_uri -d ais_engine -U ais_engine -c $db_dump_file_loc
}


docker_tests() {
    echo "Running docker image from the latest in ECR and running tests in them.."
    # export the proper CNAME for the container to run against
    export ENGINE_DB_HOST=$staging_db_uri
    # Spin up docker container from latest AIS image from ECR and test against staging database
    docker-compose -f ais-test-compose.yml up --build -d
    # Run engine and API tests
    docker exec ais bash -c 'cd /ais && . ./env/bin/activate && pytest /ais/ais/api/tests/'
}


# Once confirmed good, deploy latest AIS image from ECR to staging
deploy_to_staging_ecs() {
    echo "Deploying latest AIS image from ECR to $staging_color environment.."
    # pipe to null because they're quite noisy
    echo "running aws ecs update-service.."
    aws ecs update-service --cluster ais-$staging_color-cluster \
    --service ais-$staging_color-api-service --force-new-deployment --region us-east-1 \
    1> /dev/null
    echo "running aws ecs services-stabl.."
    aws ecs wait services-stable --cluster ais-$staging_color-cluster \
    --service ais-$staging_color-api-service --region us-east-1 \
    1> /dev/null
}


# Check staging target group health
check_target_health() {
    echo "Confirming target group health.."
    aws elbv2 describe-target-health --target-group-arn $staging_tg_arn | grep "\"healthy\"" 1> /dev/null
}


# Warm up load balancer against staging env?
warmup_lb() {
    echo "Warming up the load balancer."
    send_teams "Warming up the load balancer."
    python warmup_lb.py
    if [ $? -ne 0 ]
    then
      echo "Warmup failed"
      send_teams "AIS load balancer warmup failed.\nEngine build has been pushed but not deployed."
      exit 1;
    fi
}


# Important step! Swaps the prod environments in Route 53!!
swap_cnames() {
    # https://stackoverflow.com/a/14203146
    # accept one argument of -c for color of blue or green
    POSITIONAL=()
    while [[ $# -gt 0 ]]; do
      key="$1"

      case $key in
        -c|--color)
          COLOR="$2"
          shift # past argument
          shift # past value
          ;;
      esac
    done
    set -- "${POSITIONAL[@]}" # restore positional parameters
    if [[ "$COLOR" != "blue" ]] && [[ "$COLOR" != "green" ]]; then
        echo "Error, -c only accepts blue or green, got: '$COLOR'."
        return 1
    fi
    # First let's swap the prod cname to our now ready-to-be-prod staging_lb_uri.
    template='{
  "Comment": "Modify %s ais record to %s",
  "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "%s.",
        "Type": "CNAME",
        "TTL": 5,
        "ResourceRecords": [{ "Value": "%s" }]
    }}]
}'
    json_string=$(printf "$template" "prod" "$COLOR" "$PROD_ENDPOINT" "$staging_lb_uri")
    echo "$json_string" > $WORKING_DIRECTORY/route53-prod-change.json
    #cat $WORKING_DIRECTORY/route53-prod-change.json
    aws route53 change-resource-record-sets \
        --hosted-zone-id $PHILACITY_ZONE_ID \
        --change-batch file://$WORKING_DIRECTORY/route53-prod-change.json 1> /dev/null

    # Then alter the staging cname back to what was just the prod_lb_uri
    json_string=$(printf "$template" "stage" "$staging_color" "$STAGE_ENDPOINT" "$prod_lb_uri")
    echo "$json_string" > $WORKING_DIRECTORY/route53-stage-change.json
    #cat $WORKING_DIRECTORY/route53-stage-change.json
    aws route53 change-resource-record-sets \
        --hosted-zone-id $PHILACITY_ZONE_ID \
        --change-batch file://$WORKING_DIRECTORY/route53-stage-change.json 1> /dev/null

    echo "Swapped prod cname to $COLOR successfully! Staging is now ${prod_color}."
    send_teams "Swapped prod cname to $COLOR successfully! Staging is now ${prod_color}."
}


activate_venv_source_libaries

pull_repo

setup_log_files

check_load_creds

build_engine

identify_prod

#engine_tests

#api_tests

#dump_local_db

#restore_db_to_staging

#docker_tests

deploy_to_staging_ecs

check_target_health

#warmup_lb

swap_cnames -c $staging_color

echo "Finished successfully!"

