#!/usr/bin/env bash

set -e

PACKAGE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$PACKAGE_DIR"

python3 setup.py sdist --formats=gztar
python3 setup.py bdist

echo 'OK'