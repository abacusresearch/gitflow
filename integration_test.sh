#!/usr/bin/env bash

set -ue

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

TEST_TEMP_DIR=`mktemp --directory --tmpdir 'gitflow-test.XXXXXXXXXX'`
TEST_VIRTUAL_ENV_INSTALL_DIR="$TEST_TEMP_DIR/install-env"
TEST_VIRTUAL_ENV_DIR="$TEST_TEMP_DIR/test-env"
TEST_WORKSPACE_DIR="$TEST_TEMP_DIR/test-workspace"

trap '{ rm -rf "$TEST_TEMP_DIR"; }' EXIT

PYTHON=`which python3`

"$PYTHON" -m venv "$TEST_VIRTUAL_ENV_INSTALL_DIR"
"$PYTHON" -m venv "$TEST_VIRTUAL_ENV_DIR"



deactivate || true



set +u
source "$TEST_VIRTUAL_ENV_INSTALL_DIR/bin/activate"
set -u

pip install --upgrade pip
pip install "$DIR/dist/gitflow-0.0.0.dev0-py2.py3-none-any.whl"

echo "git-fow executable:"
which git-flow

set +u
deactivate
set -u




set +u
source "$TEST_VIRTUAL_ENV_DIR/bin/activate"
set -u


pip install --upgrade pip
pip install "$DIR/dist/gitflow-0.0.0.dev0-py2.py3-none-any.whl"
pip install -r "$DIR/test_requirements.txt"

mkdir -p "$TEST_WORKSPACE_DIR"
cd "$TEST_WORKSPACE_DIR"

mkdir 'bin'
cat > 'bin/git-flow' <<EOF
  #!/usr/bin/env bash

  source "$TEST_VIRTUAL_ENV_INSTALL_DIR/bin/activate"
  git-flow \$@
  result=\$?
  deactivate

  exit \$result

EOF

chmod +x 'bin/git-flow'

cp -R "$DIR/test" "./test"

GIT_FLOW_EXECUTABLE="$TEST_WORKSPACE_DIR/bin/git-flow" pytest --verbose --workers auto --tests-per-worker 1 test

set +u
deactivate
set -u
