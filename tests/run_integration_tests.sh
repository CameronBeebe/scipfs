#!/bin/bash

# Exit on error
set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Function to run a test script and report its status
run_test() {
    local test_script="$1"
    echo "Running integration test: $test_script"
    if bash "$test_script"; then
        echo "✅ $test_script passed"
        return 0
    else
        echo "❌ $test_script failed"
        return 1
    fi
}

# Find and run all shell-based integration tests
INTEGRATION_DIR="$SCRIPT_DIR/integration"
FAILED_TESTS=0

for test_script in "$INTEGRATION_DIR"/test_*.sh; do
    if [ -f "$test_script" ]; then
        if ! run_test "$test_script"; then
            FAILED_TESTS=$((FAILED_TESTS + 1))
        fi
    fi
done

# Report overall status
if [ $FAILED_TESTS -eq 0 ]; then
    echo "All integration tests passed!"
    exit 0
else
    echo "$FAILED_TESTS integration test(s) failed"
    exit 1
fi 