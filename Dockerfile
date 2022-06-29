#FROM python:3.6.13-slim-stretch
FROM python:3.6.15-slim-bullseye
MAINTAINER CityGeo

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install nginx gcc git build-essential vim -y && \
    apt-get clean -y && \
    apt-get autoremove -y

#RUN git clone https://github.com/CityOfPhiladelphia/ais /ais
#RUN git clone https://github.com/CityOfPhiladelphia/ais --branch roland-dev-branch-10-15-21 --single-branch /ais
#RUN git clone https://github.com/CityOfPhiladelphia/ais --branch roland_testing --single-branch /ais
COPY . /ais

# https://github.com/CityOfPhiladelphia/ais/blob/master/requirements.server.txt
# Make the AIS cloned into the root, /ais

RUN cd /ais && \
    python -m venv env && \
    . ./env/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.app.txt

RUN mkdir /ais/instance

COPY docker-build-files/50x.html /var/www/html/50x.html
COPY docker-build-files/nginx.conf /etc/nginx/nginx.conf

COPY election_block.csv /ais/env/src/passyunk/passyunk/pdata/election_block.csv
COPY usps_zip4s.csv /ais/env/src/passyunk/passyunk/pdata/usps_zip4s.csv

COPY docker-build-files/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh", "$ENGINE_DB_HOST", "$ENGINE_DB_PASS"]
