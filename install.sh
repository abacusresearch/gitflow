#!/usr/bin/env bash

set -e

PACKAGE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

pip3 install $@ --upgrade --force-reinstall "$PACKAGE_DIR"

echo 'OK'