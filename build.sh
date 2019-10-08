#!/usr/bin/env bash

set -ue

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

cd "$DIR"

pip install -r build_requirements.txt -r requirements.txt -r test_requirements.txt

python setup.py sdist --formats=gztar
python setup.py bdist
python setup.py bdist_wheel
pytest --verbose --workers auto --tests-per-worker 1 test
