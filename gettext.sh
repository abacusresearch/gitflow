#!/usr/bin/env bash

set -e

PACKAGE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$PACKAGE_DIR"

python2 /usr/bin/pygettext.py -d gen/translations gitflow/*.py