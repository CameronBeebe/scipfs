#!/bin/bash
# Script to test the scipfs_go_helper executable directly

EXECUTABLE_NAME="./scipfs_go_helper" # Assuming it's in the current directory after build
IPFS_API_ADDR="/ip4/127.0.0.1/tcp/5001" # Default, can be changed if needed

# Known CID for testing (empty directory)
TEST_CID="QmUNLLsPACCz1vLxQVkXqqLX5R1X345qqfHbsf67hvA3Nn"

PASSED_COUNT=0
FAILED_COUNT=0
TEST_COUNT=0

# Function to run a test
# $1: Test description
# $2: Expected exit code (e.g., 0 for success, 1 for expected error)
# $3...: Command and arguments to run
run_test() {
    DESCRIPTION=$1
    EXPECTED_EXIT_CODE=$2
    shift 2 # Shift past description and expected exit code
    COMMAND_TO_RUN=("$@")
    
    TEST_COUNT=$((TEST_COUNT + 1))

    echo "---------------------------------------------------"
    echo "TEST ($TEST_COUNT): $DESCRIPTION"
    echo "EXPECTED EXIT CODE: $EXPECTED_EXIT_CODE"
    echo "COMMAND: ${COMMAND_TO_RUN[@]}"

    OUTPUT_STDOUT=$("${COMMAND_TO_RUN[@]}" 2> >(tee /tmp/stderr.txt >&2) )
    ACTUAL_EXIT_CODE=$?
    OUTPUT_STDERR=$(cat /tmp/stderr.txt)
    rm /tmp/stderr.txt

    echo "ACTUAL EXIT CODE: $ACTUAL_EXIT_CODE"
    echo "STDOUT: $OUTPUT_STDOUT"
    if [ -n "$OUTPUT_STDERR" ]; then
        echo "STDERR: $OUTPUT_STDERR"
    fi

    if [ $ACTUAL_EXIT_CODE -eq $EXPECTED_EXIT_CODE ]; then
        echo "STATUS: PASSED"
        PASSED_COUNT=$((PASSED_COUNT + 1))
        # Further checks for STDOUT/STDERR content can be added here if needed
        # Example for version check:
        # if [ "$DESCRIPTION" == "Get wrapper version" ]; then
        #     if [[ "$OUTPUT_STDOUT" != *'"version":"0.1.0"'* ]]; then
        #         echo "SUB-FAIL: Version string mismatch in STDOUT!"
        #         # This would ideally mark the main test as failed too.
        #     fi
        # fi
    else
        echo "STATUS: FAILED (Expected exit code $EXPECTED_EXIT_CODE, got $ACTUAL_EXIT_CODE)"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
    echo "---------------------------------------------------"
    echo ""
}

# --- Test Cases ---

echo ">>> Starting SciPFS Go Helper Direct Tests <<<"

# Check if executable exists
if [ ! -f "$EXECUTABLE_NAME" ]; then
    echo "ERROR: $EXECUTABLE_NAME not found. Please build it first using build_go_wrapper.sh"
    exit 1
fi

# Test 1: Get version
run_test "Get wrapper version" 0 "$EXECUTABLE_NAME" version
# Add specific check for version output if desired
# if [[ "$OUTPUT_STDOUT" != *"\"version\":\"0.1.0\""* ]]; then PASSED_ALL=false; echo "FAIL: Version string mismatch"; fi 

# Test 2: Pin a known CID
# Ensure IPFS daemon is running for this test
run_test "Pin known CID ($TEST_CID)" 0 "$EXECUTABLE_NAME" -api "$IPFS_API_ADDR" pin "$TEST_CID"

# Test 3: Attempt to pin an invalid CID
run_test "Attempt to pin an invalid CID (error expected)" 1 "$EXECUTABLE_NAME" -api "$IPFS_API_ADDR" pin "invalidCIDstructure"
# This test should FAIL (exit code non-zero) and print JSON error to stderr
# We can refine the check here to assert exit code is 1 and stderr contains expected error structure

# Test 4: Call with no subcommand
run_test "Call with no subcommand (error expected)" 1 "$EXECUTABLE_NAME" -api "$IPFS_API_ADDR"
# Expected: Exit code 1, error on stderr

# Test 5: Call with unknown subcommand
run_test "Call with unknown subcommand (error expected)" 1 "$EXECUTABLE_NAME" -api "$IPFS_API_ADDR" foobar
# Expected: Exit code 1, error on stderr

# Test 6: Find providers for a known CID
# First, ensure the CID is pinned locally so this node is a provider
echo "Pre-requisite for Test 6: Pinning $TEST_CID to ensure local provider..."
"$EXECUTABLE_NAME" -api "$IPFS_API_ADDR" pin "$TEST_CID" > /dev/null 2>&1
PIN_EXIT_CODE=$?
if [ $PIN_EXIT_CODE -ne 0 ]; then
    echo "WARNING: Pre-requisite pin command for Test 6 failed. Test may be unreliable."
fi
run_test "Find providers for known CID ($TEST_CID)" 0 "$EXECUTABLE_NAME" -api "$IPFS_API_ADDR" find_providers_cid --cid "$TEST_CID" --num-providers 5
# Add specific check for find_providers_cid output
if [ $ACTUAL_EXIT_CODE -eq 0 ]; then # Only check STDOUT if command was successful
    if [[ "$OUTPUT_STDOUT" != *'"success":true'* ]]; then
        echo "SUB-FAIL (Test 6): 'success:true' not found in STDOUT!"
        # This would ideally be integrated into run_test to mark FAILED_COUNT
        # For now, manual observation or a more complex run_test function is needed
        # To properly fail the test here, we could increment FAILED_COUNT and decrement PASSED_COUNT
        # if the main status was PASSED.
    elif [[ "$OUTPUT_STDOUT" != *'"providers":['* ]] || [[ "$OUTPUT_STDOUT" == *'"providers":[]'* ]]; then
        # Check if "providers" key exists and is not an empty array.
        # A more robust check would parse JSON (e.g. with jq) if available.
        echo "SUB-FAIL (Test 6): 'providers' array not found or is empty in STDOUT!"
    fi
fi

# --- Summary --- 
echo ">>> Test Run Summary <<<"
echo "Total Tests: $TEST_COUNT"
echo "Passed: $PASSED_COUNT"
echo "Failed: $FAILED_COUNT"

if [ $FAILED_COUNT -eq 0 ]; then
    echo "All direct tests on $EXECUTABLE_NAME PASSED."
    exit 0
else
    echo "One or more direct tests on $EXECUTABLE_NAME FAILED."
    echo "Please review the output above."
    exit 1
fi 