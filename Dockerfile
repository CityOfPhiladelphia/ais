FROM python:3.10.8-slim-bullseye
MAINTAINER CityGeo

# note, have these declared in your .env file and then use docker-compose to build
# only docker-compose uses .env files
ENV ENGINE_DB_HOST=$ENGINE_DB_HOST
ENV ENGINE_DB_PASS=$ENGINE_DB_PASS
ENV GREEN_ENGINE_CNAME=$GREEN_ENGINE_CNAME
ENV BLUE_ENGINE_CNAME=$BLUE_ENGINE_CNAME

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install nginx gcc git build-essential vim dnsutils -y && \
    apt-get clean -y && \
    apt-get autoremove -y

# Automated key for accessing private git repo
RUN mkdir /root/.ssh && chmod 600 /root/.ssh
# Add github to the list of known hosts so our SSH pip installs work later
RUN ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
COPY ssh-config /root/.ssh/config 
COPY passyunk-private.key /root/.ssh/passyunk-private.key
RUN chmod 600 /root/.ssh/config; chmod 600 /root/.ssh/passyunk-private.key

# Make the AIS cloned into the root, /ais
# Note: Install python reqs at the system level, no need for venv in a docker container
# also caused some issues for me.
RUN mkdir -p /ais
RUN git clone https://github.com/CityOfPhiladelphia/ais --branch master /ais
RUN pip install --upgrade pip && \
    pip install -r /ais/requirements.txt

# Copy our secrets into the flask speciic secret path
COPY ./instance/config.py /ais/instance/config.py

# Actually install our AIS package
RUN cd /ais && pip3 install .
RUN mkdir -p /ais/instance

COPY docker-build-files/50x.html /var/www/html/50x.html
COPY docker-build-files/nginx.conf /etc/nginx/nginx.conf
COPY docker-build-files/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh
ENTRYPOINT /entrypoint.sh $ENGINE_DB_HOST $ENGINE_DB_PASS
