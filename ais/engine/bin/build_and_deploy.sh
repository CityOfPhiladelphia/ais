#!/usr/bin/env bash
# V2 worked on by Roland

# exit when any command fails
set -e
# Debug bash output (prints every command run)
#set -x
dev_deploy=false

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
        "--dev-deploy" )
            dev_deploy=true;;
        *) echo >&2 "Invalid option: $@"; exit 1;;
   esac
done

if $dev_deploy; then
    echo "#############################"
    echo "Dev deploy selected, will deploy to dev RDS instead of staging and skip ECS deployment steps."
    echo -e '\n'
else
    echo "#############################"
    echo "Production deploy selected, will deploy to staging RDS and do ECS deployment steps."
    echo -e '\n'
fi

# Enable ERR trap inheritance
set -o errtrace

# Cleanup command that will run if something in the script fails.
function cleanup {
    echo "Error! Exited prematurely at $BASH_COMMAND!!"
    echo "running reenable_taskin_alarm.."
    reenable_taskin_alarm
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
#source $WORKING_DIRECTORY/ais/engine/bin/ais-config.sh

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
      echo -e "\nChecking for still running '$1' processes..."
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
        source $WORKING_DIRECTORY/venv/bin/activate
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
ensure_passyunk_updated() {
    echo -e "\nUpdating passyunk_automation specifically.."
    file $WORKING_DIRECTORY/ssh-config
    file $WORKING_DIRECTORY/passyunk-private.key
    cp $WORKING_DIRECTORY/ssh-config ~/.ssh/config 
    cp $WORKING_DIRECTORY/passyunk-private.key ~/.ssh/passyunk-private.key
    pip install git+ssh://git@private-git/CityOfPhiladelphia/passyunk_automation.git --upgrade
    pip install git+https://github.com/CityOfPhiladelphia/passyunk --upgrade
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
    python3 $WORKING_DIRECTORY/write-secrets-to-env.py
    file $WORKING_DIRECTORY/config.py
    file $WORKING_DIRECTORY/instance/config.py
    file $WORKING_DIRECTORY/.env
    source $WORKING_DIRECTORY/.env
}


# Make sure our creds for AWS are correct and account names match our profile names.
check_aws_creds() {
    file ~/.aws/credentials
    # Default will be for our citygeo account
    aws sts get-caller-identity --profile default | grep '880708401960'
    aws sts get-caller-identity --profile mulesoft | grep '975050025792'
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
    else
        export staging_color="blue"
    fi

    # dynamically retrieve ARNs and DNS information because resources could be dynamically re-made by terraform.
    export staging_tg_arn=$(aws elbv2 describe-target-groups | grep "${staging_color}-tg" | grep TargetGroupArn| cut -d"\"" -f4)
    export prod_tg_arn=$(aws elbv2 describe-target-groups | grep "${prod_color}-tg" | grep TargetGroupArn| cut -d"\"" -f4)

    export prod_lb_uri=$(aws elbv2 describe-load-balancers --names ais-${prod_color}-api-alb --query "LoadBalancers[*].DNSName" --output text)
    export staging_lb_uri=$(aws elbv2 describe-load-balancers --names ais-${staging_color}-api-alb --query "LoadBalancers[*].DNSName" --output text)

    export prod_db_uri=$(aws rds describe-db-instances --db-instance-identifier ais-engine-${prod_color} --query "DBInstances[*].Endpoint.Address" --output text)
    export staging_db_uri=$(aws rds describe-db-instances --db-instance-identifier ais-engine-${staging_color} --query "DBInstances[*].Endpoint.Address" --output text)
    export dev_db_uri=$(aws rds describe-db-instances --db-instance-identifier ais-engine-upgrade-dev --query "DBInstances[*].Endpoint.Address" --output text)

    if $dev_deploy; then
        staging_db_uri=$dev_db_uri
    fi
}


# Clean up old docker images/containers so we don't run out of storage.
cleanup_docker() {
    # TEMP stop docker to conserve memory
    # don't fail on this, so pipe to true
    echo "Attempting to stop docker containers if they exist..."
    docker stop ais 2>/dev/null || true
    docker rm ais 2>/dev/null || true

    # Cleanup any other containers that may or may not exist.
    yes | docker system prune
    yes | docker image prune
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
    echo -e "\nRunning engine tests, comparing local build tables against what is currently in prod RDS ($prod_db_uri).."
    # Set these so it'll use the prod RDS instance

    # Compare prod against local
    export ENGINE_TO_TEST='localhost'
    export ENGINE_TO_COMPARE=$prod_db_uri

    # Unused by the engine pytests, but required by ais/__init__.py to start up ais at all.
    export ENGINE_DB_HOST=$ENGINE_TO_TEST

    export ENGINE_DB_PASS=$RDS_ENGINE_DB_PASS
    cd $WORKING_DIRECTORY
    pytest $WORKING_DIRECTORY/ais/tests/engine -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_engine_tests
    use_exit_status $? "Engine tests failed" "Engine tests passed"
    # unset
}


api_tests() {
    echo -e "\nRunning api_tests..."
    cd $WORKING_DIRECTORY
    # Set these so it'll use our local build for API tests
    export ENGINE_DB_HOST='localhost'
    export ENGINE_DB_PASS=$LOCAL_ENGINE_DB_PASS
    pytest $WORKING_DIRECTORY/ais/tests/api -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_api_tests 
    use_exit_status $? "API tests failed" "API tests passed"
}


# Make a copy (Dump) the newly built local engine db
dump_local_db() {
    echo -e "\nDumping the newly built engine database to $DB_DUMP_FILE_LOC"
    send_teams "\nDumping the newly built engine database to $DB_DUMP_FILE_LOC"
    export PGPASSWORD=$LOCAL_ENGINE_DB_PASS
    mkdir -p $WORKING_DIRECTORY/ais/engine/backup
    pg_dump -Fcustom -Z0 --create --clean -U ais_engine -h localhost -n public ais_engine > $DB_DUMP_FILE_LOC
    use_exit_status $? "DB dump failed" "DB dump succeeded"
}


deploy_to_dev_rds() {
    echo -e "\nRunning deploy_to_dev_rds.."
    echo "Restoring the engine DB to $dev_db_uri"
    send_teams "Restoring the engine DB to $dev_db_uri"

    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    db_pretty_size=$(psql -U postgres -h $dev_db_uri -d ais_engine -AXqtc "SELECT pg_size_pretty( pg_database_size('ais_engine') );")
    echo "Database size before restore: $db_pretty_size"

    # Wait for instance status to be "available" and not "modifying".
    check_rds_instance "ais-engine-upgrade-dev"

    # Manually drop and recreate the schema, mostly because extension recreates aren't included in a pg_dump
    # We need to make extensions first to get shape field functionality, otherwise our restore won't work.
    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    psql -U postgres -h $dev_db_uri -d ais_engine -c "DROP SCHEMA IF EXISTS public CASCADE;"
    # Recreate as ais_engine otherwise things get angry
    export PGPASSWORD=$RDS_ENGINE_DB_PASS
    psql -U ais_engine -h $dev_db_uri -d ais_engine -c "CREATE SCHEMA public;"
    psql -U ais_engine -h $dev_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO postgres;"
    psql -U ais_engine -h $dev_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO public;"

    # Extensions can only be re-installed as postgres superuser
    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    psql -U postgres -h $dev_db_uri -d ais_engine -c "CREATE EXTENSION postgis WITH SCHEMA public;"
    psql -U postgres -h $dev_db_uri -d ais_engine -c "CREATE EXTENSION pg_trgm WITH SCHEMA public;"
    psql -U postgres -h $dev_db_uri -d ais_engine -c "GRANT ALL ON TABLE public.spatial_ref_sys TO ais_engine;"

    # Will have lots of errors about things not existing during DROP statements because of manual public schema drop & remake but will be okay.
    export PGPASSWORD=$RDS_ENGINE_DB_PASS
    echo "Beginning restore with file $DB_DUMP_FILE_LOC, full command is:"
    echo "time pg_restore -v -j 6 -h $dev_db_uri -d ais_engine -U ais_engine -c $DB_DUMP_FILE_LOC || true"
    # Store output so we can determine if errors are actually bad
    restore_output=$(time pg_restore -v -j 6 -h $dev_db_uri -d ais_engine -U ais_engine -c $DB_DUMP_FILE_LOC || true)
    #echo $restore_output | grep 'errors ignored on restore'
    sleep 10

    # Check size after restore
    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    db_pretty_size=$(psql -U postgres -h $dev_db_uri -d ais_engine -AXqtc "SELECT pg_size_pretty( pg_database_size('ais_engine') );")
    echo "Database size after restore: $db_pretty_size"
    send_teams "Database size after restore: $db_pretty_size"

    # Assert the value is greater than 8000 MB
    db_size=$(echo $db_pretty_size | awk '{print $1}')
    # Make sure size we got is not less than 8 GB
    if [ "$db_size" -lt 8 ]; then
        echo "Database size after restore is less than 8 GB!!"
        exit 1
    else
        echo "Database size after restore looks good (greater than 8 GB)."
    fi

    # After restore, switch back to default RDS parameter group
    #aws rds modify-db-instance --db-instance-identifier $stage_instance_identifier --db-parameter-group-name default.postgres12 --apply-immediately --no-cli-pager
    sleep 60

    # Wait for instance status to be "available" and not "modifying" or "backing-up". Can be triggered by restores it seems.
    check_rds_instance "ais-engine-upgrade-dev"

    sleep 60
}


restart_staging_db() {
    echo -e "\nRestarting RDS instance: $staging_db_uri"
    echo "********************************************************************************************************"
    echo "Please make sure the RDS instance identifier names are set to 'ais-engine-green' and 'ais-engine-blue'!!"
    echo "We reboot the RDS instance by those names with the AWS CLI commmand 'aws rds reboot-db-instance'."
    echo "********************************************************************************************************"
    if [[ "$prod_color" == "blue" ]]; then
        local stage_instance_identifier="ais-engine-green"
        aws rds reboot-db-instance --region "us-east-1" --db-instance-identifier "ais-engine-green" --no-cli-pager | grep "DBInstanceStatus"
    else
        local stage_instance_identifier="ais-engine-blue"
        aws rds reboot-db-instance --region "us-east-1" --db-instance-identifier "ais-engine-blue" --no-cli-pager | grep "DBInstanceStatus"
    fi

    # Check to see if the instance is ready
    local max_attempts=30
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
        instance_status=$(aws rds describe-db-instances --region "us-east-1" \
          --db-instance-identifier "$stage_instance_identifier" \
          --query "DBInstances[0].DBInstanceStatus" --output text --no-cli-pager)

        if [ "$instance_status" = "available" ]; then
            echo "RDS instance is ready!"
            break
        fi

        echo "Waiting for RDS instance to be ready... (Attempt: $attempt/$max_attempts)"
        sleep 10
        ((attempt++))
    done

    if [ $attempt -gt $max_attempts ]; then
        echo "RDS instance did not become ready within the expected time."
        exit 1
    fi
}


# Check to see if the RDS instance is in an "available" state.
check_rds_instance() {

    # check for passed identifier, otherwise default to identifying by color
    target_db_identifier=$1

    # Initial sleep of 6 minutes because we're seeing the instance be available
    # and then suddenly in a modifying state, so parameter group modification can take longer than we expect.
    echo 'Checking RDS instance status for instance '$target_db_identifier'..'
    sleep 160

    # If target_db_identifier is empty, then try to determin the target
    if [ -z "$target_db_identifier" ]; then
        if [[ "$prod_color" == "blue" ]]; then
            local target_db_identifier="ais-engine-green"
        else
            local target_db_identifier="ais-engine-blue"
        fi
    fi
    echo 'Target RDS instance identifier is '$target_db_identifier

    local max_attempts=90
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
        instance_status=$(aws rds describe-db-instances --region "us-east-1" \
          --db-instance-identifier "$target_db_identifier" \
          --query "DBInstances[0].DBInstanceStatus" --output text --no-cli-pager)

        if [ "$instance_status" = "available" ]; then
            echo "RDS instance is ready!"
            break
        fi

        echo "Waiting for RDS instance to be ready... (Attempt: $attempt/$max_attempts)"
        sleep 10
        ((attempt++))
    done

    if [ $attempt -gt $max_attempts ]; then
        echo "RDS instance did not become ready within the expected time."
        exit 1
    fi
}


modify_stage_scaling_out() {
    # either disable or enable
    action=$1

    # 1 disable staging taskout action that scales out containers
    if [[ "$action" == 'disable' ]]; then
        echo 'Disabling ECS tasks and scale out..'
        # 1. disable staging taskout action that scales out containers
        aws cloudwatch disable-alarm-actions --alarm-names ais-${staging_color}-api-taskout
        # 2. Set desired tasks to 0 so they don't blow up the db with health checks while restoring.
        aws ecs update-service --cluster ais-${staging_color}-cluster --service ais-${staging_color}-api-service --desired-count 0
    elif [[ "$action" == 'enable' ]]; then
        echo 'Reenabling ECS tasks and scale out..'
        aws cloudwatch enable-alarm-actions --alarm-names ais-${staging_color}-api-taskout
        # Must allow back at least 1 instance so our later checks on the target groups works.
        aws ecs update-service --cluster ais-${staging_color}-cluster --service ais-${staging_color}-api-service --desired-count 2
    fi
}


# Update (Restore) AWS RDS instance to staging database
# Note: you can somewhat track restore progress by looking at the db size:
#SELECT pg_size_pretty( pg_database_size('ais_engine') );
restore_db_to_staging() {
    echo -e "\nRunning restore_db_to_staging.."
    echo "Restoring the engine DB to $staging_db_uri"
    send_teams "Restoring the engine DB to $staging_db_uri"

    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    db_pretty_size=$(psql -U postgres -h $staging_db_uri -d ais_engine -AXqtc "SELECT pg_size_pretty( pg_database_size('ais_engine') );")
    echo "Database size before restore: $db_pretty_size"


    # Get production color
    if [[ "$prod_color" == "blue" ]]; then
        local stage_instance_identifier="ais-engine-green"
    else
        local stage_instance_identifier="ais-engine-blue"
    fi

    #######################
    # First let's modify parameters of the DB so restores go a bit faster

    # Commands to create custom restore parameter group
    #aws rds create-db-parameter-group --db-parameter-group-name ais-restore-parameters --db-parameter-group-family postgres12 --description "Params to speed up restore, DO NOT USE FOR PROD TRAFFIC"

    # Change RDS instance to use faster but less "safe" restore parameters
    # Unfortunately RDS does not allow us to modify "full_page_writes" which would definitely speed up restoring.
    # loosely based off https://www.databasesoup.com/2014/09/settings-for-fast-pgrestore.html
    # and https://stackoverflow.com/a/75147585

    # This command actually modifies the parameter group "ais-restore-parameters" each time. Just nice to have the changes it makes explicitly in code.
    #aws rds modify-db-parameter-group \
    #    --db-parameter-group-name ais-restore-parameters \
    #    --parameters "ParameterName=max_wal_size,ParameterValue=5120,ApplyMethod='immediate'" \
    #    --parameters "ParameterName=max_wal_senders,ParameterValue=0,ApplyMethod='immediate'" \
    #    --parameters "ParameterName=wal_keep_segments,ParameterValue=0,ApplyMethod='immediate'" \
    #    --parameters "ParameterName=autovacuum,ParameterValue=off,ApplyMethod='immediate'" \
    #    --parameters "ParameterName=shared_buffers,ParameterValue='{DBInstanceClassMemory/65536}',ApplyMethod='pending-reboot'" \
    #    --parameters "ParameterName=synchronous_commit,ParameterValue=off,ApplyMethod='immediate'" \
    #    --no-cli-pager

    # modify stage rds to use restore parameter group
    #aws rds modify-db-instance --db-instance-identifier $stage_instance_identifier --db-parameter-group-name ais-restore-parameters --apply-immediately --no-cli-pager

    # Wait for instance status to be "available" and not "modifying".
    check_rds_instance $stage_instance_identifier

    # Manually drop and recreate the schema, mostly because extension recreates aren't included in a pg_dump
    # We need to make extensions first to get shape field functionality, otherwise our restore won't work.
    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    psql -U postgres -h $staging_db_uri -d ais_engine -c "DROP SCHEMA IF EXISTS public CASCADE;"
    # Recreate as ais_engine otherwise things get angry
    export PGPASSWORD=$RDS_ENGINE_DB_PASS
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "CREATE SCHEMA public;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO postgres;"
    psql -U ais_engine -h $staging_db_uri -d ais_engine -c "GRANT ALL ON SCHEMA public TO public;"

    # Extensions can only be re-installed as postgres superuser
    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    psql -U postgres -h $staging_db_uri -d ais_engine -c "CREATE EXTENSION postgis WITH SCHEMA public;"
    psql -U postgres -h $staging_db_uri -d ais_engine -c "CREATE EXTENSION pg_trgm WITH SCHEMA public;"
    psql -U postgres -h $staging_db_uri -d ais_engine -c "GRANT ALL ON TABLE public.spatial_ref_sys TO ais_engine;"

    # Will have lots of errors about things not existing during DROP statements because of manual public schema drop & remake but will be okay.
    export PGPASSWORD=$RDS_ENGINE_DB_PASS
    echo "Beginning restore with file $DB_DUMP_FILE_LOC, full command is:"
    echo "time pg_restore -v -j 6 -h $staging_db_uri -d ais_engine -U ais_engine -c $DB_DUMP_FILE_LOC || true"
    # Store output so we can determine if errors are actually bad
    restore_output=$(time pg_restore -v -j 6 -h $staging_db_uri -d ais_engine -U ais_engine -c $DB_DUMP_FILE_LOC || true)
    #echo $restore_output | grep 'errors ignored on restore'
    sleep 10

    # Check size after restore
    export PGPASSWORD=$RDS_SUPER_ENGINE_DB_PASS
    db_pretty_size=$(psql -U postgres -h $staging_db_uri -d ais_engine -AXqtc "SELECT pg_size_pretty( pg_database_size('ais_engine') );")
    echo "Database size after restore: $db_pretty_size"
    send_teams "Database size after restore: $db_pretty_size"

    # Assert the value is greater than 8000 MB
    db_size=$(echo $db_pretty_size | awk '{print $1}')
    # Make sure size we got is not less than 8 GB
    if [ "$db_size" -lt 8 ]; then
        echo "Database size after restore is less than 8 GB!!"
        exit 1
    else
        echo "Database size after restore looks good (greater than 8 GB)."
    fi

    # After restore, switch back to default RDS parameter group
    #aws rds modify-db-instance --db-instance-identifier $stage_instance_identifier --db-parameter-group-name default.postgres12 --apply-immediately --no-cli-pager
    sleep 60

    # Wait for instance status to be "available" and not "modifying" or "backing-up". Can be triggered by restores it seems.
    check_rds_instance $stage_instance_identifier

    sleep 60
}


engine_tests_for_restored_rds() {
    echo -e "Running engine tests, testing $staging_db_uri and comparing to $prod_db_uri.."
    # Set these so it'll use the prod RDS instance

    # Compare stage against prod
    export ENGINE_TO_TEST=$staging_db_uri
    export ENGINE_TO_COMPARE=$prod_db_uri

    # Unused by the engine pytests, but required by ais/__init__.py to start up ais at all.
    export ENGINE_DB_HOST=$ENGINE_TO_TEST
    export ENGINE_DB_PASS=$RDS_ENGINE_DB_PASS

    cd $WORKING_DIRECTORY
    pytest $WORKING_DIRECTORY/ais/tests/engine -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_engine_tests
    use_exit_status $? "Engine tests failed" "Engine tests passed"
    # unset
}


docker_tests() {
    echo -e "\nRunning docker_tests, which pulls the docker image from the latest in ECR and runs tests.."
    # Set these so it'll use the staging RDS instance
    export ENGINE_DB_HOST=$staging_db_uri
    export ENGINE_DB_PASS=$RDS_ENGINE_DB_PASS
    # Login to ECR so we can pull the image, will  use our AWS creds sourced from .env
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 880708401960.dkr.ecr.us-east-1.amazonaws.com

    # Pull our latest docker image
    docker pull 880708401960.dkr.ecr.us-east-1.amazonaws.com/ais:latest
    # Spin up docker container from latest AIS image from ECR and test against staging database
    # Note: the compose uses the environment variables for the database and password that we exported earlier
    docker-compose -f ecr-test-compose.yml up --build -d
    # Run API tests
    docker exec ais bash -c "pytest /ais/ais/tests/api/ -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_api_tests"
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
    python $WORKING_DIRECTORY/ais/engine/bin/warmup_lb.py --dbpass $LOCAL_ENGINE_DB_PASS --gatekeeper-key $GATEKEEPER_KEY
    use_exit_status $? \
        "AIS load balancer warmup failed.\nEngine build has been pushed but not deployed." \
        "AIS load balancer warmup succeeded.\nEngine build has been pushed and deployed."
}


# Important step! Swaps the prod environments in Route 53!!
swap_cnames() {
    echo -e "\nSwapping prod/stage CNAMEs..."
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

    # Swap the production DNS record to the ALB DNS we identified as staging
    json_string=$(printf "$template" "prod" "$prod_color" "$PROD_ENDPOINT" "$staging_lb_uri")
    echo "Swapping ${prod_color} to the Prod record in hosted zone ${CITYGEOPHILACITY_ZONE_ID}.."
    echo "$json_string" > $WORKING_DIRECTORY/route53-temp-change.json
    aws route53 change-resource-record-sets \
        --hosted-zone-id $CITYGEOPHILACITY_ZONE_ID \
        --profile default \
        --change-batch file://$WORKING_DIRECTORY/route53-temp-change.json 1> /dev/null
    echo "Swapping ${prod_color} to the Prod record in hosted zone ${PHILACITY_ZONE_ID}.."
    aws route53 change-resource-record-sets \
        --hosted-zone-id $PHILACITY_ZONE_ID \
        --profile default \
        --change-batch file://$WORKING_DIRECTORY/route53-temp-change.json 1> /dev/null


    # Swap the staging DNS record to the ALB DNS we identified as prod
    json_string=$(printf "$template" "stage" "$staging_color" "$STAGE_ENDPOINT" "$prod_lb_uri")
    echo "Swapping ${staging_color} to the Stage record in hosted zone ${CITYGEOPHILACITY_ZONE_ID}.."
    echo "$json_string" > $WORKING_DIRECTORY/route53-temp-change.json
    aws route53 change-resource-record-sets \
        --hosted-zone-id $CITYGEOPHILACITY_ZONE_ID \
        --profile default \
        --change-batch file://$WORKING_DIRECTORY/route53-temp-change.json 1> /dev/null
    echo "Swapping ${staging_color} to the Stage record in hosted zone ${PHILACITY_ZONE_ID}.."
    aws route53 change-resource-record-sets \
        --hosted-zone-id $PHILACITY_ZONE_ID \
        --profile default \
        --change-batch file://$WORKING_DIRECTORY/route53-temp-change.json 1> /dev/null

    echo "Swapped prod cname to ${staging_color} successfully! Staging is now ${prod_color}."
}


reenable_taskin_alarm() {
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
    #python $WORKING_DIRECTORY/ais/engine/bin/make_reports.py
    send_teams "Making Reports..."
    bash $WORKING_DIRECTORY/ais/engine/bin/make_reports.sh
    send_teams "Reports have completed!"
    
}

check_for_prior_runs

activate_venv_source_libaries

ensure_passyunk_updated

setup_log_files

check_load_creds

git_pull_ais_repo

check_aws_creds

identify_prod

cleanup_docker

build_engine

engine_tests

api_tests

dump_local_db

if $dev_deploy; then
    echo "Dev deploy flag is set to true, skipping production deploys to the blue/green environments."
    docker_tests

    deploy_to_dev_rds

else
    modify_stage_scaling_out "disable"

    restart_staging_db

    restore_db_to_staging

    engine_tests_for_restored_rds

    modify_stage_scaling_out "enable"

    docker_tests

    scale_up_staging

    deploy_to_staging_ecs

    check_target_health

    warmup_lb

    swap_cnames

    reenable_taskin_alarm

    make_reports_tables
fi

echo "Finished successfully!"
