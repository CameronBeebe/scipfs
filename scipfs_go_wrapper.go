package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/ipfs/boxo/path" // This is the correct import for the path type returned by kubo client
	files "github.com/ipfs/boxo/files" // Use boxo/files for Node type compatibility
	cid "github.com/ipfs/go-cid"         // Import the go-cid package
	rpc "github.com/ipfs/kubo/client/rpc" // Renamed import to avoid conflict
	ma "github.com/multiformats/go-multiaddr"
)

// CommandResponse structure for JSON output
type CommandResponse struct {
	Success bool        `json:"success"`
	Error   string      `json:"error,omitempty"`
	Data    interface{} `json:"data,omitempty"`
}

// Add a simple struct for the ID command response
type IDResponse struct {
	ID              string   `json:"ID"`
	AgentVersion    string   `json:"AgentVersion"`
	ProtocolVersion string   `json:"ProtocolVersion"`
	Addresses       []string `json:"Addresses"`
}

const WrapperVersion = "0.1.0" // Define the wrapper version

func printJSONResponse(success bool, errorMsg string, data interface{}) {
	resp := CommandResponse{
		Success: success,
		Error:   errorMsg,
		Data:    data,
	}
	jsonBytes, err := json.Marshal(resp)
	if err != nil {
		// Fallback if JSON marshaling fails
		// Ensure this also goes to stderr if it's an error case for the whole command
		errorResponse := CommandResponse{Success: false, Error: "Failed to marshal JSON response: " + err.Error()}
		errorJsonBytes, _ := json.Marshal(errorResponse)
		fmt.Fprintln(os.Stderr, string(errorJsonBytes))
		os.Exit(1) // Exit after printing, as this is an unrecoverable state for the wrapper.
		return
	}

	if success {
		fmt.Println(string(jsonBytes))
	} else {
		fmt.Fprintln(os.Stderr, string(jsonBytes)) // Print actual error to stderr
		os.Exit(1) // Exit with error code
	}
}

func main() {
	// --- Global Flags ---
	globalFlags := flag.NewFlagSet(os.Args[0], flag.ExitOnError)
	apiAddrStr := globalFlags.String("api", "/ip4/127.0.0.1/tcp/5001", "IPFS daemon API multiaddress")

	args := os.Args[1:]

	// Attempt to parse global flags from the beginning of the arguments.
	// flag.Parse will stop at the first non-flag argument.
	err := globalFlags.Parse(args)
	if err != nil {
		// For flag.ExitOnError, a fatal flag error would have exited.
		// If we are here, it might be a less severe issue or it simply stopped.
		// We can print the error for debugging if necessary, but often globalFlags.Args() will have what we need.
		// fmt.Fprintln(os.Stderr, "Debug: Global flag parsing encountered an issue (or stopped):", err)
	}

	// The remaining arguments after global flag parsing are the subcommand and its arguments.
	nonFlagArgs := globalFlags.Args()
	var subcommand string
	var subcommandArgs []string

	if len(nonFlagArgs) > 0 {
		subcommand = nonFlagArgs[0]
		subcommandArgs = nonFlagArgs[1:]
	} else {
		// No subcommand found after global flags (or no args at all other than flags)
		printJSONResponse(false, "Subcommand required after global flags (e.g., version, pin, add_file)", nil)
		return
	}

	// --- IPFS Node Connection ---
	var node *rpc.HttpApi

	apiMaddr, err := ma.NewMultiaddr(*apiAddrStr)
	if err != nil {
		printJSONResponse(false, fmt.Sprintf("Invalid API multiaddress '%s': %s", *apiAddrStr, err.Error()), nil)
		return
	}

	// Context for API calls (not for NewApi itself if it doesn't take it)
	// connectCtx, connectCancel := context.WithTimeout(context.Background(), 10*time.Second)
	// defer connectCancel()

	node, err = rpc.NewApi(apiMaddr) // Removed context from NewApi call
	if err != nil {
		printJSONResponse(false, fmt.Sprintf("Failed to connect to IPFS node at %s: %s", *apiAddrStr, err.Error()), nil)
		return
	}

	// A simple ID check to confirm connection
	// We'll use the generic Request for the ID command
	idCtx, idCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer idCancel()

	var idOutput IDResponse // Use the struct for unmarshalling
	err = node.Request("id").Exec(idCtx, &idOutput) // Use generic request for /id
	if err != nil {
		printJSONResponse(false, fmt.Sprintf("Failed to get ID from IPFS node at %s (connection check failed): %s", *apiAddrStr, err.Error()), nil)
		return
	}
	// If successful, idOutput is populated. We don't need to print it here, just check error.

	// --- Subcommand Handling ---
	switch subcommand {
	case "version":
		printJSONResponse(true, "", map[string]string{"version": WrapperVersion})
	case "daemon_info": // New subcommand to get daemon info (ID, Version etc.)
		// The ID was already fetched during the connection check. We can reuse idOutput.
		// If we wanted to fetch fresh, we'd call node.Request("id").Exec(ctx, &idOutput) again.
		printJSONResponse(true, "", idOutput)
	case "pin":
		pinCmd := flag.NewFlagSet("pin", flag.ExitOnError)
		err := pinCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'pin' subcommand: %s", err.Error()), nil)
			return
		}

		argsForPin := pinCmd.Args()
		if len(argsForPin) < 1 {
			printJSONResponse(false, "CID argument required for pin command", nil)
			return
		}
		cidStr := argsForPin[0]

		// First, validate the CID string itself to ensure it's a well-formed CID
		_, cidErr := cid.Decode(cidStr)
		if cidErr != nil {
			printJSONResponse(false, fmt.Sprintf("Invalid CID format for '%s': %s", cidStr, cidErr.Error()), nil)
			return
		}

		// Construct the full IPFS path string
		ipfsPathStr := "/ipfs/" + cidStr

		// Now create the path object using the full path string
		p, pathErr := path.NewPath(ipfsPathStr)
		if pathErr != nil {
			// This error would typically indicate issues with the path string itself, even if the CID part was valid
			printJSONResponse(false, fmt.Sprintf("Error creating IPFS path object for '%s': %s", ipfsPathStr, pathErr.Error()), nil)
			return
		}

		ctxPin, cancelPin := context.WithTimeout(context.Background(), 60*time.Second)
		defer cancelPin()

		err = node.Pin().Add(ctxPin, p)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Failed to pin IPFS path '%s': %s", ipfsPathStr, err.Error()), nil)
			return
		}
		printJSONResponse(true, "", map[string]string{"cid": cidStr, "path": ipfsPathStr, "status": "pinned"})

	case "add_file":
		addFileCmd := flag.NewFlagSet("add_file", flag.ExitOnError)
		filePath := addFileCmd.String("file", "", "Path to the file to add")
		// Potentially add other flags like --pin, --raw-leaves etc. later if needed.

		err := addFileCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'add_file' subcommand: %s", err.Error()), nil)
			return
		}

		if *filePath == "" {
			printJSONResponse(false, "Argument --file <path> is required for add_file command", nil)
			return
		}

		// Validate file path and get FileInfo
		fileInfo, err := os.Stat(*filePath)
		if err != nil {
			if os.IsNotExist(err) {
				printJSONResponse(false, fmt.Sprintf("File not found: %s", *filePath), nil)
			} else {
				printJSONResponse(false, fmt.Sprintf("Error accessing file '%s': %s", *filePath, err.Error()), nil)
			}
			return
		}

		if fileInfo.IsDir() {
			printJSONResponse(false, fmt.Sprintf("Path '%s' is a directory, please provide a file to add.", *filePath), nil)
			return
		}

		// Create a files.Node for the IPFS API.
		// files.NewSerialFile is suitable for adding a single file from a path.
		fnode, err := files.NewSerialFile(*filePath, false, fileInfo)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error creating file node for '%s': %s", *filePath, err.Error()), nil)
			return
		}
		// defer fnode.Close() // files.Node from boxo/files might not need explicit Close like go-ipfs-files, or it's handled differently.
		// Check documentation if issues arise. For SerialFile, usually data is read at creation or first access.

		ctxAdd, cancelAdd := context.WithTimeout(context.Background(), 120*time.Second) // 2 minute timeout for add
		defer cancelAdd()

		// Add the file via Unixfs API
		// We are not using any options.UnixfsAddOption for now (e.g. Pinning, RawLeaves).
		// Pinning will be handled by a separate call to the "pin" subcommand from the Python client if needed.
		// The return type of node.Unixfs().Add is path.ImmutablePath from "github.com/ipfs/boxo/path"
		addedPath, err := node.Unixfs().Add(ctxAdd, fnode)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Failed to add file '%s' to IPFS: %s", *filePath, err.Error()), nil)
			return
		}

		// Use RootCid() method from github.com/ipfs/boxo/path.ImmutablePath
		cidValue := addedPath.RootCid() // CORRECTED to RootCid()
		if !cidValue.Defined() {
			printJSONResponse(false, fmt.Sprintf("Failed to get a defined CID for file '%s'", *filePath), nil)
			return
		}
		printJSONResponse(true, "", map[string]string{"cid": cidValue.String()})

	default:
		printJSONResponse(false, fmt.Sprintf("Unknown subcommand: '%s'. Args provided: %v", subcommand, subcommandArgs), nil)
	}
} 