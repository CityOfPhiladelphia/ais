#!/usr/bin/env bash
# V2 worked on by Roland

# exit when any command fails
set -e
# Debug bash output (prints every command run)
#set -x

# Accept tests to skip
while [[ $# -gt 0 ]] && [[ "$1" == "--"* ]] ;
do
    opt="$1";
    shift;              #expose next argument
    case "$opt" in
        "--" ) break 2;;
        "--skip-api-tests" )
           skip_api_tests=="$1"; shift;;
        "--skip-api-tests="* )
           skip_api_tests=="${opt#*=}";;
        "--skip-engine-tests" )
           skip_engine_tests="$1"; shift;;
        "--skip-engine-tests="* )
           skip_engine_tests="${opt#*=}";;
        *) echo >&2 "Invalid option: $@"; exit 1;;
   esac
done


# Enable ERR trap inheritance
set -o errtrace

# Cleanup command that will run if something in the script fails.
function cleanup {
    echo "Error! Exited prematurely at $BASH_COMMAND!!"
    echo "running reenable_alarm.."
    reenable_alarm
}
trap cleanup ERR


WORKING_DIRECTORY=/home/ubuntu/ais
LOG_DIRECTORY=$WORKING_DIRECTORY/ais/engine/log
cd $WORKING_DIRECTORY
echo "Working directory is $WORKING_DIRECTORY"

git_commit=$(git rev-parse HEAD)
git_branch=$(git rev-parse --abbrev-ref HEAD)
echo "Current git commit id is: $git_commit, branch: $git_branch"

# Has our send_teams and get_prod_env functions
source $WORKING_DIRECTORY/ais/engine/bin/ais-utils.sh
source $WORKING_DIRECTORY/ais/engine/bin/ais-config.sh

# dump location used in mutltiple functions, so export it.
export DB_DUMP_FILE_LOC=$WORKING_DIRECTORY/ais/engine/backup/ais_engine.dump
# Remove it to start fresh and save disk space
rm -f $DB_DUMP_FILE_LOC

# NOTE: postgres connection information is also stored in ~/.pgpass!!!
# postgres commands should use passwords in there depending on the hostname.

datestamp=$(date +%Y-%m-%d)
start_dt=$(date +%Y%m%d%T)
echo "Started: "$start_dt


use_exit_status() {
    # Use exit status to send correct success/failure message to Teams and console
    # $1 int - exit status, typically of last process via $?
    # $2 text - failure message to echo and send to Teams
    # $3 text - success message to echo and send to Teams

    if [ $1 -ne 0 ]
    then
        echo "$2"
        send_teams "$2"
        exit 1;
    else
        echo "$3"
        send_teams "$3"
    fi
}


check_for_prior_runs() {
    kill_subfunction() {
      # Find the pid of the process, if it's still running, and then kill it.
      echo "Checking for still running '$1' processes..."
      pids=( $(ps ax | grep "bash $1" | grep -v grep | awk '{ print $1 }') )
      # Check the number of processes found.
      # If it's greater than 2, it means multiple instances are running.
      if [ ${#pids[@]} -gt 2 ]; then
        echo "Multiple instances of '$1' are running."
        # Kill all instances except for the current one.
        for pid in "${pids[@]}"; do
          if [ "$pid" != "$BASHPID" ]; then
            echo "Killing process with PID: $pid"
            kill $pid
          fi
        done
      else
        echo "'$1' is not currently running multiple instances."
      fi
    }
    # Check for build_and_deploy.sh processes
    kill_subfunction "build_and_deploy.sh"
    # Also check for build_engine.sh commands that could potentially be running
    # without an invoking build_and_deploy.sh also running. Stranger things have happened.
    kill_subfunction "build_engine.sh"
}


activate_venv_source_libaries() {
    if [ ! -d $WORKING_DIRECTORY/venv ]; then
        echo -e "\nActivating/creating venv.."
        python3.10 -m venv $WORKING_DIRECTORY/venv 
        source $WORKING_DIRECTORY/env/bin/activate
        # Add the ais folder with our __init__.py so we can import it as a python module
        export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
        pip install wheel
        # Add github to the list of known hosts so our SSH pip installs work later
        ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
        pip install -r $WORKING_DIRECTORY/requirements.txt
    else
        echo "Activating virtual environment"
        source $WORKING_DIRECTORY/venv/bin/activate
        # Add the ais folder with our __init__.py so we can import it as a python module
        export PYTHONPATH="${PYTHONPATH}:$WORKING_DIRECTORY/ais"
    fi
}


# not always a given
ensure_private_repos_updated() {
    file $WORKING_DIRECTORY/ssh-config
    file $WORKING_DIRECTORY/passyunk-private.key
    cp $WORKING_DIRECTORY/ssh-config ~/.ssh/config 
    cp $WORKING_DIRECTORY/passyunk-private.key ~/.ssh/passyunk-private.key
    pip install git+ssh://git@private-git/CityOfPhiladelphia/passyunk_automation.git
}


git_pull_ais_repo() {
    cd $WORKING_DIRECTORY
    git fetch
    git pull
    cd -
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
    echo -e "\nLoading credentials and passwords into the environment"
    file $WORKING_DIRECTORY/config.py
    file $WORKING_DIRECTORY/instance/config.py
    file $WORKING_DIRECTORY/.env
    source $WORKING_DIRECTORY/.env
}


# Get AWS production environment
identify_prod() {
    echo -e "\nFinding the production environment via CNAME"
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
    echo -e "\nStarting new engine build"
    send_teams "Starting new engine build."
    bash $WORKING_DIRECTORY/ais/engine/bin/build_engine.sh > >(tee -a $out_file_loc) 2> >(tee -a $error_file_loc >&2)
    send_teams "Engine build has completed."
    end_dt=$(date +%Y%m%d%T)
    echo "Time Summary: "
    echo "Started: "$start_dt
    echo "Finished: "$end_dt
}


engine_tests() {
    echo -e "\nRunning engine tests against locally built database."
    # Note: imports instance/config.py for credentials
    cd $WORKING_DIRECTORY
    pytest $WORKING_DIRECTORY/ais/tests/engine -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_engine_tests 
    use_exit_status $? "Engine tests failed" "Engine tests passed"
}


api_tests() {
    echo -e "\nRunning api_tests..."
    cd $WORKING_DIRECTORY
    pytest $WORKING_DIRECTORY/ais/tests/api -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_api_tests 
    use_exit_status $? "API tests failed" "API tests passed"
}


# Make a copy (Dump) the newly built local engine db
dump_local_db() {
    echo -e "\nRunning dump_local_db...."
    # TEMP stop docker to conserve memory
    # don't fail on this, so pipe to true
    echo "Attempting to stop docker containers if they exist..."
    docker stop ais 2>/dev/null || true
    docker rm ais 2>/dev/null || true
    echo "Dumping the newly built engine database.."
    send_teams "Dumping the newly built engine database.."
    export PGPASSWORD=$LOCAL_ENGINE_DB_PASS
    mkdir -p $WORKING_DIRECTORY/ais/engine/backup
    pg_dump -Fc -U ais_engine -h localhost -n public ais_engine > $DB_DUMP_FILE_LOC
    use_exit_status $? "DB dump failed" "DB dump succeeded"
}


# Update (Restore) AWS RDS instance to staging database
# Note: you can somewhat track restore progress by looking at the db size:
#SELECT pg_size_pretty( pg_database_size('ais_engine') );
restore_db_to_staging() {
    echo -e "\nRunning restore_db_to_staging.."
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
    echo "Beginning restore with file $DB_DUMP_FILE_LOC.."
    # Ignore failures, many of them are trying to drop non-existent tables (which our schema drop earlier handles)
    # or restore postgis specific tables that our extensions handles.
    # We should rely on db tests passing instead.
    pg_restore --verbose -h $staging_db_uri -d ais_engine -U ais_engine -c $DB_DUMP_FILE_LOC || true
    # Print size after restore
    export PGPASSWORD=$PG_ENGINE_DB_PASS
    echo 'Database size after restore:'
    psql -U postgres -h $staging_db_uri -d ais_engine -c "SELECT pg_size_pretty( pg_database_size('ais_engine') );"

}


docker_tests() {
    echo -e "\nRunning docker_tests, which pulls the docker image from the latest in ECR and runs tests.."
    # export the proper CNAME for the container to run against
    export ENGINE_DB_HOST=$staging_db_uri
    # Login to ECR so we can pull the image, will  use our AWS creds sourced from .env
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 880708401960.dkr.ecr.us-east-1.amazonaws.com
    # Spin up docker container from latest AIS image from ECR and test against staging database
    # Note: the compose uses the environment variables for the database and password that we exported earlier
    docker-compose -f ecr-test-compose.yml up --build -d
    # Run engine and API tests
    docker exec ais bash -c "pytest /ais/ais/tests/api/ -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_api_tests"
}


test_prod_db() {
    export ENGINE_DB_HOST='stage_db_uri'
    export ENGINE_DB_PASS=$LOCAL_DB_PASS
    docker compose -f build-test-compose.yml build --no-cache
}


scale_up_staging() {
    echo -e "\nRunning scale_up_staging..."
    prod_tasks=$(aws ecs describe-clusters --clusters ais-${prod_color}-cluster | grep runningTasksCount | tr -s ' ' | cut -d ' ' -f3 | cut -d ',' -f1)
    echo -e "\nCurrent running tasks in prod: $prod_tasks"
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
    echo -e "\nDeploying latest AIS image from ECR to $staging_color environment.."
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
    echo -e "\nConfirming target group health.."
    aws elbv2 describe-target-health --target-group-arn $staging_tg_arn | grep "\"healthy\"" 1> /dev/null
}


# Warm up load balancer against staging env?
warmup_lb() {
    echo -e "\nWarming up the load balancer for staging lb: $staging_color."
    # Export creds again so this function can access them.
    file $WORKING_DIRECTORY/.env
    source $WORKING_DIRECTORY/.env
    send_teams "Warming up the load balancer for staging lb: $staging_color."
    python $WORKING_DIRECTORY/ais/engine/bin/warmup_lb.py --dbpass $LOCAL_PASSWORD --gatekeeper-key $GATEKEEPER_KEY
    use_exit_status $? \
        "AIS load balancer warmup failed.\nEngine build has been pushed but not deployed." \
        "AIS load balancer warmup succeeded.\nEngine build has been pushed and deployed."
}


# Important step! Swaps the prod environments in Route 53!!
swap_cnames() {
    echo -e "\nSwapping prod/stage CNAMEs..."
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
    aws route53 change-resource-record-sets \
        --hosted-zone-id $PHILACITY_ZONE_ID \
        --change-batch file://$WORKING_DIRECTORY/route53-prod-change.json 1> /dev/null

    # Then alter the staging cname back to what was just the prod_lb_uri
    json_string=$(printf "$template" "stage" "$staging_color" "$STAGE_ENDPOINT" "$prod_lb_uri")
    echo "$json_string" > $WORKING_DIRECTORY/route53-stage-change.json
    aws route53 change-resource-record-sets \
        --hosted-zone-id $PHILACITY_ZONE_ID \
        --change-batch file://$WORKING_DIRECTORY/route53-stage-change.json 1> /dev/null

    echo "Swapped prod cname to $COLOR successfully! Staging is now ${prod_color}."
    send_teams "Swapped prod cname to $COLOR successfully! Staging is now ${prod_color}."
}


reenable_alarm() {
    echo -e "\nSleeping for 5 minutes, then running scale-in alarm re-enable command..."
    sleep 300
    aws cloudwatch enable-alarm-actions --alarm-names ais-${staging_color}-api-taskin
    echo "Alarm 'ais-${staging_color}-api-taskin' re-enabled."
}


# Runs various scripts that make necessary "report" tables off our built AIS tables that
# aren't used by AIS.
# These are used by other departments for various integrations, mainly related
# to unique identifier for addresses. For example for DOR we call this PIN.
make_reports_tables() {
    echo -e "\nRunning engine make_reports.py script..."
    python $WORKING_DIRECTORY/ais/engine/bin/make_reports.py || true
}

check_for_prior_runs

activate_venv_source_libaries

ensure_private_repos_updated

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
