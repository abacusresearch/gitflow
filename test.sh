#!/usr/bin/env bash

set -ue

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

cd "$DIR"

pytest --verbose --workers auto --tests-per-worker 1 test
