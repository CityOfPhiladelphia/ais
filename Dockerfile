FROM python:3.14.7-slim-trixie
MAINTAINER CityGeo

# note, have these declared in your .env file and then use docker-compose to build
# only docker-compose uses .env files
ENV ENGINE_DB_HOST=$ENGINE_DB_HOST
ENV ENGINE_DB_PASS=$ENGINE_DB_PASS
ENV GREEN_ENGINE_CNAME=$GREEN_ENGINE_CNAME
ENV BLUE_ENGINE_CNAME=$BLUE_ENGINE_CNAME

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install gcc git build-essential vim dnsutils secure-delete -y && \
    apt-get clean -y && \
    apt-get autoremove -y

# Add github to the list of known hosts so our SSH pip installs work later
RUN ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
# config so we can hit private repos via ssh
COPY ssh-config /root/.ssh/config

# Note: Install python reqs at the system level, no need for venv in a docker container
# also caused some issues for me.
# Install them first so code changes are less likely to re-trigger a full requirements reinstall
RUN mkdir -p /ais
COPY requirements.txt /ais/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /ais/requirements.txt

# Make the AIS cloned into the root, /ais
COPY . /ais
# Copy our secrets into the flask speciic secret path
COPY ./instance/config.py /ais/instance/config.py

# Actually install our AIS package
RUN cd /ais && pip3 install .
RUN mkdir -p /ais/instance

COPY docker-build-files/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh
ENTRYPOINT /entrypoint.sh $ENGINE_DB_HOST $ENGINE_DB_PASS
