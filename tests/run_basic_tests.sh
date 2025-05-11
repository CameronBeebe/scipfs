#!/bin/bash

# Basic integration tests for scipfs
# Assumes IPFS daemon is running and scipfs is installed.

set -e # Exit immediately if a command exits with a non-zero status.
# set -x # Uncomment for detailed command tracing

TEST_LIB_NAME="scipfs_test_lib_$$ " # Use PID to avoid collisions
TEST_FILE_NAME="test_file_$$.txt"
TEST_FILE_CONTENT="Hello from scipfs test $$"
DOWNLOAD_DIR="./scipfs_test_downloads_$$"
DOWNLOADED_FILE="$DOWNLOAD_DIR/$TEST_FILE_NAME"
CONFIG_DIR="$HOME/.scipfs"
MANIFEST_FILE="$CONFIG_DIR/${TEST_LIB_NAME}_manifest.json"

echo "--- SciPFS Basic Integration Test Start ---"

# --- Cleanup Function --- 
cleanup() {
    echo "--- Cleaning up --- "
    rm -f "$TEST_FILE_NAME"
    rm -rf "$DOWNLOAD_DIR"
    # Cautiously remove the test manifest if it exists
    if [[ -f "$MANIFEST_FILE" ]]; then
        echo "Removing test manifest: $MANIFEST_FILE"
        rm "$MANIFEST_FILE"
    else
        echo "Test manifest not found or already removed: $MANIFEST_FILE"
    fi
    echo "Cleanup complete."
}

# --- Trap cleanup on exit --- 
trap cleanup EXIT ERR INT TERM

# --- Test Steps --- 

# 1. Ensure config dir exists (run init)
 echo "[Test] Running scipfs init..."
 scipfs init
 if [ ! -d "$CONFIG_DIR" ]; then
     echo "FAIL: Config directory $CONFIG_DIR not created by init."
     exit 1
 fi
 echo "OK: Init command succeeded."

# 2. Create a new library
 echo "[Test] Creating library: $TEST_LIB_NAME..."
 CREATE_OUTPUT=$(scipfs create "$TEST_LIB_NAME" | cat) # Use cat to handle potential prompts/paging
 echo "$CREATE_OUTPUT"
 MANIFEST_CID=$(echo "$CREATE_OUTPUT" | grep "Initial Manifest CID" | awk '{print $NF}')
 if [ ! -f "$MANIFEST_FILE" ]; then
     echo "FAIL: Manifest file $MANIFEST_FILE not created."
     exit 1
 fi
 if [ -z "$MANIFEST_CID" ]; then
      echo "FAIL: Could not extract Initial Manifest CID from create output."
      # Attempt to extract CID differently if format changed
      # For now, just fail
      exit 1
 fi
 echo "OK: Library created with Initial Manifest CID: $MANIFEST_CID"

# 3. List local libraries
 echo "[Test] Listing local libraries..."
 LIST_LOCAL_OUTPUT=$(scipfs list-local | cat)
 echo "$LIST_LOCAL_OUTPUT"
 if ! echo "$LIST_LOCAL_OUTPUT" | grep -q "$TEST_LIB_NAME"; then
     echo "FAIL: Test library $TEST_LIB_NAME not found in list-local output."
     exit 1
 fi
 echo "OK: list-local command includes test library."

# 4. Create a test file
 echo "[Test] Creating dummy file: $TEST_FILE_NAME..."
 echo "$TEST_FILE_CONTENT" > "$TEST_FILE_NAME"
 if [ ! -f "$TEST_FILE_NAME" ]; then
     echo "FAIL: Could not create test file $TEST_FILE_NAME."
     exit 1
 fi
 echo "OK: Dummy file created."

# 5. Add the test file to the library
 echo "[Test] Adding file '$TEST_FILE_NAME' to library '$TEST_LIB_NAME'..."
 ADD_OUTPUT=$(scipfs add "$TEST_LIB_NAME" "$TEST_FILE_NAME" | cat)
 echo "$ADD_OUTPUT"
 NEW_MANIFEST_CID=$(echo "$ADD_OUTPUT" | grep "New Manifest CID" | awk '{print $NF}')
 if [ -z "$NEW_MANIFEST_CID" ]; then
      echo "FAIL: Could not extract New Manifest CID from add output."
      exit 1
 fi
 if [ "$NEW_MANIFEST_CID" == "$MANIFEST_CID" ]; then
       echo "FAIL: Manifest CID did not change after adding a new file."
       exit 1
 fi
 echo "OK: File added, New Manifest CID: $NEW_MANIFEST_CID"

# 6. List files in the library
 echo "[Test] Listing files in library '$TEST_LIB_NAME'..."
 LIST_FILES_OUTPUT=$(scipfs list "$TEST_LIB_NAME" | cat)
 echo "$LIST_FILES_OUTPUT"
 if ! echo "$LIST_FILES_OUTPUT" | grep -q "$TEST_FILE_NAME"; then
     echo "FAIL: Test file $TEST_FILE_NAME not found in list output."
     exit 1
 fi
 FILE_CID=$(echo "$LIST_FILES_OUTPUT" | grep "$TEST_FILE_NAME" | sed -n 's/.*CID: \([^,]*\).*/\1/p')
 if [ -z "$FILE_CID" ]; then
      echo "FAIL: Could not extract File CID from list output."
      exit 1
 fi
 echo "OK: list command shows added file with CID: $FILE_CID"

# 7. Get (download) the file
 echo "[Test] Getting file '$TEST_FILE_NAME' from library '$TEST_LIB_NAME'..."
 mkdir -p "$DOWNLOAD_DIR"
 scipfs get "$TEST_LIB_NAME" "$TEST_FILE_NAME" "$DOWNLOAD_DIR" | cat
 if [ ! -f "$DOWNLOADED_FILE" ]; then
     echo "FAIL: Downloaded file $DOWNLOADED_FILE not found."
     exit 1
 fi
 echo "OK: File downloaded."

# 8. Verify downloaded file content
 echo "[Test] Verifying downloaded file content..."
 DOWNLOADED_CONTENT=$(cat "$DOWNLOADED_FILE")
 if [ "$DOWNLOADED_CONTENT" != "$TEST_FILE_CONTENT" ]; then
     echo "FAIL: Downloaded file content mismatch."
     echo "Expected: $TEST_FILE_CONTENT"
     echo "Got: $DOWNLOADED_CONTENT"
     exit 1
 fi
 echo "OK: Downloaded file content matches."

# 9. (Optional) Test joining - requires knowing the latest CID
 # echo "[Test] Joining library using latest CID..."
 # # Need to remove local manifest first to simulate joining
 # rm "$MANIFEST_FILE"
 # scipfs join "$NEW_MANIFEST_CID"
 # if [ ! -f "$MANIFEST_FILE" ]; then
 #    echo "FAIL: Manifest file $MANIFEST_FILE not recreated by join."
 #    exit 1
 # fi
 # echo "OK: Join command succeeded."

# --- Test End --- 

echo "--- SciPFS Basic Integration Test PASSED ---"
exit 0 # Explicitly exit with 0 on success 