#!/usr/bin/env bash

set -ex

source env/bin/activate
py.test ais
