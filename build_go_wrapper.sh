#!/bin/bash
# Script to build the scipfs_go_helper executable

echo ">>> Building SciPFS Go Helper <<<"

# Navigate to the directory where scipfs_go_wrapper.go is located
# Assuming this script is in the project root and scipfs_go_wrapper.go is also there.
# If scipfs_go_wrapper.go is in a subdirectory, adjust the cd command or paths.
# SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# cd "$SCRIPT_DIR" 

# Define the Go source file and output executable name
GO_SOURCE_FILE="scipfs_go_wrapper.go"
EXECUTABLE_NAME="scipfs_go_helper"
GO_MODULE_NAME="scipfs_go_wrapper" # Or your chosen module name

# Check if Go is installed
if ! command -v go &> /dev/null
then
    echo "ERROR: Go is not installed or not in PATH. Please install Go."
    exit 1
fi

echo "--- Ensuring Go module is initialized and dependencies are present ---"
if [ ! -f "go.mod" ]; then
    echo "go.mod not found. Initializing Go module: $GO_MODULE_NAME..."
    go mod init $GO_MODULE_NAME
    if [ $? -ne 0 ]; then
        echo "ERROR: 'go mod init' failed."
        exit 1
    fi
    
    echo "Fetching dependencies..."
    go get github.com/ipfs/kubo/client/rpc
    go get github.com/ipfs/boxo/path
    go get github.com/multiformats/go-multiaddr
    if [ $? -ne 0 ]; then
        echo "ERROR: 'go get' for dependencies failed."
        exit 1
    fi
else
    echo "go.mod found. Ensuring dependencies are tidy..."
    go mod tidy # Cleans up dependencies
    if [ $? -ne 0 ]; then
        echo "WARNING: 'go mod tidy' encountered issues, but attempting build anyway."
    fi
fi

echo "--- Building $EXECUTABLE_NAME from $GO_SOURCE_FILE ---"
go build -o $EXECUTABLE_NAME $GO_SOURCE_FILE

if [ $? -eq 0 ]; then
    echo "SUCCESS: Build complete! '$EXECUTABLE_NAME' created in the current directory."
    echo "If you run scipfs from this directory, ensure './$EXECUTABLE_NAME' is used or it's in your PATH."
    echo "Python IPFSClient expects it as: self.go_wrapper_executable = "$EXECUTABLE_NAME" (or with a path)"
else
    echo "ERROR: Go build failed. Please check for errors above."
    exit 1
fi

echo ">>> SciPFS Go Helper build process finished <<<" 