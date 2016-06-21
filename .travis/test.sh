#!/usr/bin/env bash

set -e

source env/bin/activate
py.test ais
