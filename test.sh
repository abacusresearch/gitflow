#!/usr/bin/env bash

set -e

PACKAGE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$PACKAGE_DIR"

py.test 'test'