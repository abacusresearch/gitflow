#!/usr/bin/env bash

set -ue

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

TEST_VIRTUAL_ENV_DIR=`mktemp --directory --tmpdir 'pytest.tmp.XXXXXXXXXX'`

trap '{ rm -rf "$TEST_VIRTUAL_ENV_DIR"; }' EXIT

PYTHON=`which python3`

rm -rf "$TEST_VIRTUAL_ENV_DIR"
"$PYTHON" -m venv "$TEST_VIRTUAL_ENV_DIR"
cd "$TEST_VIRTUAL_ENV_DIR"
deactivate || true

set +u
source "$TEST_VIRTUAL_ENV_DIR/bin/activate"
set -u

"$DIR/build.sh"

pip install --upgrade pip
#pip install --install-option test "$DIR/dist/gitflow-0.0.0.dev0-py2.py3-none-any.whl"
pip install "$DIR/dist/gitflow-0.0.0.dev0-py2.py3-none-any.whl"
pip install -r "$DIR/test_requirements.txt"
cp -R "$DIR/test" "./test"

GIT_FLOW_TEST_INSTALLED=1 pytest --verbose --workers auto --tests-per-worker 1 test

set +u
deactivate
set -u
