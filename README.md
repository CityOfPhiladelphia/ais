# Address Information System (AIS)

AIS provides a unified view of City data for an address.

[API usage documentation](https://github.com/CityOfPhiladelphia/ais/blob/master/docs/APIUSAGE.md)

## Goals

- Simplify relationships between land records, real estate properties, streets, and addresses
- Provide a way of standardizing addresses citywide
- Support applications that require geocoding and address-based data lookups
- Provide a feedback mechanism for continually improving parity between department datasets
- Deprecate legacy systems for geocoding and address standardizing

## Components

- geocoder
- address standardizer (see [passyunk](https://github.com/cityofphiladelphia/passyunk))
- integration environment for address-centric data
- API

## Development

To develop locally:

1. `git clone https://github.com/CityOfPhiladelphia/ais`
2. `cd ais`
3. Create and activate a [virtualenv](https://virtualenv.pypa.io/en/stable/).
4. `pip install -r requirements.txt`. You may have to work through installing some dependencies by hand, especially on Windows.
5. Copy [Passyunk](https://github.com/cityofphiladelphia/passyunk) data files. See README for more instructions.
6. Create an empty file at `/ais/instance/config.py`. To run engine scripts, you'll need to add dictionary to this called `DATABASE` mapping database names to connection strings. (TODO: commit sample instance config)
7. Rename `.env.sample` in the root directory to `.env` and add real environment settings. (TODO: commit `.env.sample`)
8. `honcho start`. This will start start serving over port 5000. Note that this is blocked on CityNet, so you'll have to be on a public network to access `http://0.0.0.0:5000`.

## Docker Container Dev

For building the docker container, you'll need some environment/build arg variables first. Copy the example .env file used with docker-compose and populate it:

1. `cp env.example .env && chmod +x .env` 
2. populate it, set the $ENGINE_DB_HOST var to your database CNAME or IP. Note that in our build deploy process at citygeo this is done automatically and is not needed.

Check to make sure docker-compose is populating your args:

1. docker-compose -f build-test-compose.yml config

Note that you may need to set ENGINE_DB_HOST to a direct IP instead of a CNAME to get it working in-office.
Now run the 'pull-private-passyunkdata.sh' script to download CSVs needed in the DockerFile.

2. `chmod +x pull-private-passyunkdata.sh; ./pull-private-passyunkdata.sh` 

Then build and start the container.

3. Via docker-compose: `docker-compose -f build-test-compose.yml up --build -d` 
    1. Directly:
```
docker build -t ais:latest .
docker run -itd --name ais -p 8080:8080 -e ENGINE_DB_HOST=$ENGINE_DB_HOST -e ENGINE_DB_PASS= $ENGINE_DB_PASS ais:latest` 
```

If the container could successfully contact the DB then it should stay up and running. You may now run tests to confirm functionality.

4. `docker exec ais bash -c 'cd /ais && . ./env/bin/activate && pytest /ais/ais/api/tests/'`

## Testing
The API and the Engine can be tested separately using pytest after sourcing the virtual environment `venv`.
```bash
pytest $WORKING_DIRECTORY/ais/tests/engine -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_engine_tests 

pytest $WORKING_DIRECTORY/ais/tests/api -vvv -ra --showlocals --tb=native --disable-warnings --skip=$skip_api_tests 
```
For reasons currently unknown, the `tests/api/test_views.py` cannot be tested on their own -- almost all the tests will fail with a 404 Response Error -- so all `api` tests must be run simultaneously.
