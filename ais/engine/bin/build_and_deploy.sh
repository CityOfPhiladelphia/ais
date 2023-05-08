#!/usr/bin/env bash
# V2 worked on by Roland

# exit when any command fails
set -e
# Debug bash output (prints every command run)
#set -x

# Accept tests to skip
while getopts "sa:se:" opt; do
  case ${opt} in
    sa|skip-api-tests ) skip_api_list=${OPTARG};;
    se|skip-engine-tests ) skip_engine_list=${OPTARG};;
  esac
done

# Print out the skip values
#echo "Skip values:"
#for skip_value in "${skip_values[@]}"; do
#  echo "$skip_value"
#done

WORKING_DIRECTORY=/home/ubuntu/ais
LOG_DIRECTORY=$WORKING_DIRECTORY/ais/engine/log

cd $WORKING_DIRECTORY
echo "Working directory is $WORKING_DIRECTORY"

# Has our send_teams and get_prod_env functions
source $WORKING_DIRECTORY/ais/engine/bin/ais-utils.sh
source $WORKING_DIRECTORY/ais/engine/bin/ais-config.sh

# dump location used in mutltiple functions, so export it.
export DB_DUMP_FILE_LOC=$WORKING_DIRECTORY/ais/engine/backup/ais_engine.dump
# Remove it to start fresh and save disk space
rm -f $DB_DUMP_FILE_LOC


trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# echo an error message before exiting
trap 'echo "Exited prematurely, running reenable_alarm.."; reenable_alarm; echo "\"${last_command}\" command exited with code $?."' EXIT

# NOTE: postgres connection information is also stored in ~/.pgpass!!!
# postgres commands should use passwords in there depending on the hostname.

datestamp=$(date +%Y-%m-%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt


activate_venv_source_libaries() {
    if [ ! -d $WORKING_DIRECTORY/venv ]; then
        echo "Activating/creating venv.."
        python3.10 -m venv $WORKING_DIRECTORY/venv 
        source $WORKING_DIRECTORY/env/bin/activate
        # Add the ais folder with our __init__.py so we can import it as a python module
        export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
	# used for python3.5, not needed with the pip version that's installed under 3.6
        # Looks like pip 18.1 works and is what we want.
        #pip install --upgrade "pip < 21.0"
        pip install wheel
	# Add github to the list of known hosts so our SSH pip installs work later
	ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
	pip install git+https://github.com/CityOfPhiladelphia/passyunk
 	pip install git+ssh://git@private-git/CityOfPhiladelphia/passyunk_automation.git
	# used for python3.5
        #python setup.py bdist_wheel 
        #pip install -r $WORKING_DIRECTORY/requirements.txt || deactivate && rm $WORKING_DIRECTORY/env -rf && exit 1
        #pip install -r $WORKING_DIRECTORY/requirements.txt
        pip install -r $WORKING_DIRECTORY/requirements-build.txt

        # Install AIS as a python module, needed in tests.
        python setup.py develop
    else
        echo "Activating virtual environment"
        source $WORKING_DIRECTORY/venv/bin/activate
        # Add the ais folder with our __init__.py so we can import it as a python module
        export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
    fi
}


git_pull_ais_repo() {
    cd $WORKING_DIRECTORY
    git fetch
    git pull
    cd -
}


pull_passyunk_repo() {
#    echo "Ensuring necessary repos are updated from github"
    # GET LATEST CODE FROM GIT REPO
    # passyunk public repo
    pip install git+https://github.com/CityOfPhiladelphia/passyunk
    # passyunk private repo that pulls in csvs
    # note the URL is private-git, this is a custom SSH host specified in out SSH config
    # file, /root/.ssh/config that is installed in our Dockerfile.
    pip install git+ssh://git@private-git/CityOfPhiladelphia/passyunk_automation.git
}


# CREATE ENGINE LOG FILES
setup_log_files() {

    mkdir -p $LOG_DIRECTORY
    error_file="build_errors_"
    out_file="build_log_"
    error_file_loc=$LOG_DIRECTORY/$error_file$datestamp.txt
    out_file_loc=$LOG_DIRECTORY/$out_file$datestamp.txt
    warmup_lb_error_file_loc=$LOG_DIRECTORY/warmup_lb_error-$datestamp.txt
    touch $error_file_loc
    touch $out_file_loc
    touch $warmup_lb_error_file_loc
}


# Check for and load credentials
# This wil be needed for the engine build to pull in data.
# config-secrets.sh contains AWS 
check_load_creds() {
    echo "Loading credentials and passwords into the environment"
    # 11/9/22 Note: No longer needed with Jame's changes. pdata is installed via pip
    #. $WORKING_DIRECTORY/pull-private-passyunkdata.sh
    #cp $WORKING_DIRECTORY/docker-build-files/election_block.csv $WORKING_DIRECTORY/env/src/passyunk/passyunk/pdata/
    #cp $WORKING_DIRECTORY/docker-build-files/usps_zip4s.csv $WORKING_DIRECTORY/env/src/passyunk/passyunk/pdata/

    #set +x
    file $WORKING_DIRECTORY/config.py
    file $WORKING_DIRECTORY/instance/config.py
    file $WORKING_DIRECTORY/.env
    source $WORKING_DIRECTORY/.env
    #set -x
}


# Get AWS production environment
identify_prod() {
    echo "Finding the production environment via CNAME"
    # export to environment var so it can be accessed by sub-python scripts run in this script.
    export prod_color=$(get_prod_env || {
      echo "Could not find the production environment" ;
      exit 1 ;
    })
    echo "Production environment is: $prod_color"
    if [[ "$prod_color" == "blue" ]]; then
        export staging_color="green" 
        staging_db_uri=$GREEN_ENGINE_CNAME
        staging_lb_uri=$GREEN_CNAME

        prod_db_uri=$BLUE_ENGINE_CNAME
        prod_lb_uri=$BLUE_CNAME
    else
        export staging_color="blue"
        staging_db_uri=$BLUE_ENGINE_CNAME
        staging_lb_uri=$BLUE_CNAME

        prod_db_uri=$GREEN_ENGINE_CNAME
        prod_lb_uri=$GREEN_CNAME
    fi
    export staging_tg_arn=$(aws elbv2 describe-target-groups | grep "${staging_color}-tg" | grep TargetGroupArn| cut -d"\"" -f4)
    export prod_tg_arn=$(aws elbv2 describe-target-groups | grep "${prod_color}-tg" | grep TargetGroupArn| cut -d"\"" -f4)
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


engine_tests() {
    echo "Running engine tests against locally built database."
    cd $WORKING_DIRECTORY
    # Note: imports instance/config.py for credentials
    # If we received skipped engine tests argument
    if [ ! -z "$skip_engine_list" ]; then
        pytest $WORKING_DIRECTORY/ais/engine/tests/test_engine.py -vvv -ra --showlocals --tb=native --skip=$skip_engine_list
    else
        pytest $WORKING_DIRECTORY/ais/engine/tests/test_engine.py -vvv -ra --showlocals --tb=native
    fi

    if [ $? -ne 0 ]
    then
      echo "Engine tests failed"
      send_teams "Engine tests have failed."
      exit 1;
    fi
    send_teams "Engine tests have passed."
}


api_tests() {
    echo "Running api_tests..."
    cd $WORKING_DIRECTORY

    # If we received skipped engine tests argument
    if [ ! -z "$skip_engine_list" ]; then
        pytest $WORKING_DIRECTORY/ais/api/tests/ -vvv -ra --showlocals --tb=native --skip=$skip_api_list
    else
        pytest $WORKING_DIRECTORY/ais/engine/tests/test_engine.py -vvv -ra --showlocals --tb=native
    fi

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
    echo "Running dump_local_db...."
    # TEMP stop docker to conserve memory
    # don't fail on this, so pipe to true
    echo "Attempting to stop docker containers if they exist..."
    docker stop ais || true
    docker rm ais || true
    echo "Dumping the newly built engine database.."
    send_teams "Dumping the newly built engine database.."
    export PGPASSWORD=$LOCAL_ENGINE_DB_PASS
    mkdir -p $WORKING_DIRECTORY/ais/engine/backup
    pg_dump -Fc -U ais_engine -h localhost -n public ais_engine > $DB_DUMP_FILE_LOC
    if [ $? -ne 0 ]
    then
      echo "DB dump failed"
      exit 1;
    fi
}


# Update (Restore) AWS RDS instance to staging database
# Note: you can somewhat track restore progress by looking at the db size:
#SELECT pg_size_pretty( pg_database_size('ais_engine') );
restore_db_to_staging() {
    echo "Running restore_db_to_staging.."
    echo "Restoring the engine DB to $staging_db_uri"
    send_teams "Restoring the engine DB to $staging_db_uri"
    export PGPASSWORD=$ENGINE_DB_PASS
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "DROP SCHEMA IF EXISTS public CASCADE;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "CREATE SCHEMA public;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO postgres;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO public;"
    # Extensions must be re-installed and can only be done as superuser
    export PGPASSWORD=$PG_ENGINE_DB_PASS
    psql -U postgres -h $staging_db_uri -d ais_engine -c "CREATE EXTENSION postgis;"
    psql -U postgres -h $staging_db_uri -d ais_engine -c "CREATE EXTENSION pg_trgm;"
    export PGPASSWORD=$ENGINE_DB_PASS
    #pg_restore -h $staging_db_uri -d ais_engine -U ais_engine -c $db_dump_file_loc || :
    echo "Beginning restore with file $DB_DUMP_FILE_LOC.."
    # Ignore failures, many of them are trying to drop non-existent tables (which our schema drop earlier handles)
    # Or restore postgis specific tablse that our extensions handles
    # We should rely on db tests passing instead.
    pg_restore --verbose -h $staging_db_uri -d ais_engine -U ais_engine -c $DB_DUMP_FILE_LOC || true
    # Print size after restore
    export PGPASSWORD=$PG_ENGINE_DB_PASS
    echo 'Database size after restore:'
    psql -U postgres -h ais-engine-green.cfuoybzycpox.us-east-1.rds.amazonaws.com -d ais_engine -c "SELECT pg_size_pretty( pg_database_size('ais_engine') );"

}


docker_tests() {
    echo "Running docker_tests, which pulls the docker image from the latest in ECR and runs tests.."
    # export the proper CNAME for the container to run against
    export ENGINE_DB_HOST=$staging_db_uri
    # Login to ECR so we can pull the image, will  use our AWS creds sourced from .env
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 880708401960.dkr.ecr.us-east-1.amazonaws.com
    # Spin up docker container from latest AIS image from ECR and test against staging database
    docker-compose -f ais-test-compose.yml up --build -d
    # Run engine and API tests
    docker exec ais bash -c 'cd /ais && pytest /ais/ais/api/tests/ -vvv -ra --showlocals --tb=native'
}


scale_up_staging() {
    echo "Running scale_up_staging..."
    prod_tasks=$(aws ecs describe-clusters --clusters ais-${prod_color}-cluster | grep runningTasksCount | tr -s ' ' | cut -d ' ' -f3 | cut -d ',' -f1)
    echo "Current running tasks in prod: $prod_tasks"
    if (( $prod_tasks > 2 ))
    then
        # Must temporarily disable the alarm otherwise we'll get scaled back in seconds. We'll re-enable five minutes 
        # after switching prod and staging.
        aws cloudwatch disable-alarm-actions --alarm-names ais-${staging_color}-api-taskin
        # throw in a sleep, can take a bit for the disable action to take effect.
        sleep 15
        aws ecs update-service --cluster ais-${staging_color}-cluster --service ais-${staging_color}-api-service --desired-count ${prod_tasks}
        # Wait for cluster to be stable, e.g. all the containers are spun up.
        # For changing from 2 to 5 instances (+3) in my experience it tooks about 3 minutes for the service to become stable.
        aws ecs wait services-stable --cluster ais-${staging_color}-cluster \
        --service ais-${staging_color}-api-service --region us-east-1 
        # When we re-enable the alarm at the end of this entire script, the scalein alarm should
        # start lowering the task count by 1 slowly based on the alarm 'cooldown' time.
    else
        echo "Staging has 2 running tasks, the minimum. Not running any scaling actions."
    fi
}


# Once confirmed good, deploy latest AIS image from ECR to staging
deploy_to_staging_ecs() {
    echo "Deploying latest AIS image from ECR to $staging_color environment.."
    # pipe to null because they're quite noisy
    echo "running aws ecs update-service.."
    aws ecs update-service --cluster ais-${staging_color}-cluster \
    --service ais-${staging_color}-api-service --force-new-deployment --region us-east-1 \
    1> /dev/null
    echo "running aws ecs services-stable.."
    aws ecs wait services-stable --cluster ais-${staging_color}-cluster \
    --service ais-${staging_color}-api-service --region us-east-1 
}


# Check staging target group health
check_target_health() {
    echo "Confirming target group health.."
    aws elbv2 describe-target-health --target-group-arn $staging_tg_arn | grep "\"healthy\"" 1> /dev/null
}


# Warm up load balancer against staging env?
warmup_lb() {
    # Export creds again so this function can access them.
    file $WORKING_DIRECTORY/config-secrets.sh
    source $WORKING_DIRECTORY/config-secrets.sh
    echo "Warming up the load balancer for staging lb: $staging_color."
    send_teams "Warming up the load balancer for staging lb: $staging_color."
    python $WORKING_DIRECTORY/ais/engine/bin/warmup_lb.py --proxy $PROXY_AUTH --dbpass $LOCAL_PASSWORD --gatekeeper-key $GATEKEEPER_KEY
    if [ $? -ne 0 ]
    then
      echo "AIS load balancer warmup failed.\nEngine build has been pushed but not deployed."
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


reenable_alarm() {
    echo "Sleeping for 5 minutes, then running scale-in alarm re-enable command..."
    sleep 300
    aws cloudwatch enable-alarm-actions --alarm-names ais-${staging_color}-api-taskin
    echo "Alarm 'ais-${staging_color}-api-taskin' re-enabled."
}

make_reports_tables() {
    python $WORKING_DIRECTORY/ais/engine/bin/make_reports.py
}


activate_venv_source_libaries

# 11/9/22 Note: No longer needed with Jame's changes. pdata is installed via pip
#pull_repo

setup_log_files

check_load_creds

git_pull_ais_repo

identify_prod

build_engine

engine_tests

api_tests

dump_local_db

restore_db_to_staging

docker_tests

scale_up_staging

deploy_to_staging_ecs

check_target_health

warmup_lb

swap_cnames -c $staging_color

reenable_alarm

make_reports_tables

echo "Finished successfully!"

