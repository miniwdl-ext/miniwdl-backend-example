#!/bin/bash
#
# TO RUN THIS TEST SCRIPT:
#
#   prove -v test/test.t
#
set -o pipefail

# bootstrap bash-tap
cd "$(dirname $0)/.."
SOURCE_DIR="$(pwd)"
BASH_TAP_ROOT="$SOURCE_DIR/test/bash-tap"
source "$BASH_TAP_ROOT/bash-tap-bootstrap"

# activate plugin
pip3 install .
export MINIWDL__SCHEDULER__CONTAINER_BACKEND=example_docker_run

# provision temp test directory
DN="$(mktemp -d)"
DN="$(realpath "$DN")"
cd "$DN"
echo "$DN"

# bash-tap test plan
plan tests 2

# verify successful miniwdl run_self_test
miniwdl run_self_test --dir "$(pwd)/self_test"
is "$?" "0" "miniwdl run_self_test"

# verify workflow.log reflects active plugin
grep 'docker run :: pid' $(find self_test -name workflow.log)
is "$?" "0" "plugin active"

# clean up
rm -rf "$DN"
