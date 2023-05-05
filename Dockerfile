#FROM python:3.6.13-slim-stretch
#FROM python:3.6.15-slim-bullseye
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

# Private passyunk data now retrieved through private repo in build_go.sh
#COPY election_block.csv /ais/env/src/passyunk/passyunk/pdata/election_block.csv
#COPY usps_zip4s.csv /ais/env/src/passyunk/passyunk/pdata/usps_zip4s.csv
# Automated key for accessing private git repo
RUN mkdir /root/.ssh && chmod 600 /root/.ssh
# Add github to the list of known hosts so our SSH pip installs work later
RUN ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
COPY --chmod=0600 ssh-config /root/.ssh/config 
COPY --chmod=0600 passyunk-private.key /root/.ssh/passyunk-private.key

# https://github.com/CityOfPhiladelphia/ais/blob/master/requirements.server.txt
# Make the AIS cloned into the root, /ais
# Note: right now passyunk needs to be installed manually, doesn't work
# via requirements.txt for whatever reason
# Note: Install python reqs at the system level, no need for venv in a docker container
# also caused some issues for me.
RUN mkdir -p /ais
RUN git clone https://github.com/CityOfPhiladelphia/ais --branch python3.10-upgrade /ais
COPY requirements* /ais/
RUN pip install --upgrade pip && \
    pip install git+https://github.com/CityOfPhiladelphia/passyunk && \
    pip install git+ssh://git@private-git/CityOfPhiladelphia/passyunk_automation.git && \
    pip install -r /ais/requirements.app.txt
    #python -m venv /ais/venv && \
    #. /ais/venv/bin/activate && \

#RUN git clone https://github.com/CityOfPhiladelphia/ais --branch roland-dev-branch-10-15-21 --single-branch /ais
#RUN git clone https://github.com/CityOfPhiladelphia/ais --branch roland_testing --single-branch /ais
#COPY ais/ /ais/ais
#COPY application.py /ais/
#COPY bin/ /ais/bin/
#COPY bin/ /ais/bin/
#COPY docker-build-files/ /ais/docker-build-files/
#COPY setup.py /ais/
#COPY config.py /ais/
#COPY gunicorn.conf.py /ais/
#COPY manage.py /ais/

# Actually install our AIS package
RUN cd /ais && pip3 install .

RUN mkdir -p /ais/instance

COPY docker-build-files/50x.html /var/www/html/50x.html
COPY docker-build-files/nginx.conf /etc/nginx/nginx.conf

COPY docker-build-files/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh
#ENTRYPOINT ["/entrypoint.sh", "$ENGINE_DB_HOST", "$ENGINE_DB_PASS"]
ENTRYPOINT /entrypoint.sh $ENGINE_DB_HOST $ENGINE_DB_PASS
#CMD ["/bin/bash"]
