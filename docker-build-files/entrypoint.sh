#!/bin/bash
cd /ais


# -z mean if unset
# ! -z mean if set
if [ -z "${ENGINE_DB_PASS}" ]; then
    echo 'ENGINE_DB_PASS var not set!'
    exit 1
fi

if [ -z "${ENGINE_DB_HOST}" ]; then
    echo "Did not receive ENGINE_DB_HOST var, attempting to set manually.."
    prod_color=$(dig ais-prod.phila.city +short | grep -o "blue\|green")
    if [[ "$PROD_COLOR" -eq "blue" ]]; then
	if [ -z "${BLUE_ENGINE_CNAME}" ]; then
	    echo 'BLUE_ENGINE_CNAME var not set!'
	    exit 1
	fi
        export ENGINE_DB_HOST=$BLUE_ENGINE_CNAME
    fi
    if [[ "$PROD_COLOR" -eq "green" ]]; then
	if [ -z "${GREEN_ENGINE_CNAME}" ]; then
	    echo 'GREEN_ENGINE_CNAME var not set!'
	    exit 1
	fi
        export ENGINE_DB_HOST=$GREEN_ENGINE_CNAME
    fi
fi

if [ -z "${ENGINE_DB_HOST}" ]; then
    echo 'ENGINE_DB_HOST var not set!'
    exit 1
fi

# This line has flask serve out the app directly, only for staging
#python application.py runserver -h 0.0.0.0 -p 80

# Create the configuration file that points ais at it's ais_engine database.
echo "SQLALCHEMY_DATABASE_URI = \
    'postgresql://ais_engine:$ENGINE_DB_PASS@$ENGINE_DB_HOST:5432/ais_engine'" >> /ais/instance/config.py


#ls /ais/venv/lib/python3.10/site-packages/passyunk/pdata
#ls /ais/venv/lib/python3.10/site-packages/passyunk_automation/pdata

function fail {
    printf '%s\n' "$1" >&2 ## Send message to stderr.
    exit "${2-1}" ## Return a code specified by $2, or 1 by default.
}

declare -a pdata_files=('alias' 'alias_streets' 'apt' 'apt_std' 'apte'
 'centerline' 'centerline_streets' 'directional' 'landmarks' 'name_switch'
 'saint' 'std' 'suffix' )

# Update passyunk pdata files everytime the container starts.
echo 'Pulling in passyunk package to update pdata files with command "pip install --force-reinstall git+ssh://git@private-git/CityOfPhiladelphia/passyunk.git@master"..'
pip install --force-reinstall git+ssh://git@private-git/CityOfPhiladelphia/passyunk.git@master &>/dev/null || fail "Failed to update passyunk pdata files!!"
# Delete private ssh key once pulled and running.
srm /root/.ssh/passyunk-private.key

echo "Asserting private data is in passyunk site-package folder"
for i in "${pdata_files[@]}"
do
  test -f /usr/local/lib/python3.10/site-packages/passyunk/pdata/$i.csv || fail "$i.csv does not exist in venv!"
done

declare -a pdata_files=('election_block' 'usps_alias' 'usps_cityzip' 'usps_zip4s')

echo "Asserting private data is in passyunk_automation site-package folder"
for i in "${pdata_files[@]}"
do
  test -f /usr/local/lib/python3.10/site-packages/passyunk_automation/pdata/$i.csv || fail "$i.csv does not exist in venv!"
done
echo 'All private data exists.'

# Run nginx as proxy server to gunicorn
# running like this will start in the background
nginx

# Gunicorn will be behind nginx, run on socket. Gunicorn must be run in the /ais folder.
#gunicorn application --bind unix:/tmp/gunicorn.sock --worker-class=gevent --access-logfile '-' --log-level 'debug'
#gunicorn application --bind unix:/tmp/gunicorn.sock --workers 4 --worker-class=gevent --access-logfile '-' --log-level 'notice'
#gunicorn application --bind 0.0.0.0:8080 --workers 5 --threads 2 --worker-class gevent --access-logfile '-' --log-level 'notice'
#gunicorn application --bind 0.0.0.0:8080 --worker-connections 512 --workers 2 --worker-class gevent --access-logfile '-' --log-level 'notice'
# Nginx will proxy to the socket
gunicorn application --bind unix:/tmp/gunicorn.sock --workers 4 --worker-class gevent --access-logfile '-' --log-level 'notice'
