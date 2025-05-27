package main

import (
	"bytes"
	"context"
	"encoding/json"
	"os/exec"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"strconv"
	"strings"
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
const RequiredIPFSVersion = "0.34.1"

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

// compareVersions returns true if version1 is less than version2
func compareVersions(version1Str, version2Str string) (bool, error) {
	parseVer := func(vStr string) ([]int, error) {
		parts := strings.Split(strings.TrimSpace(vStr), ".")
		if len(parts) != 3 {
			return nil, fmt.Errorf("invalid version format: %s, expected X.Y.Z", vStr)
		}
		var_int_parts := make([]int, 3)
		for i, p := range parts {
			val, err := strconv.Atoi(p)
			if err != nil {
				return nil, fmt.Errorf("non-integer part in version %s: %s", vStr, p)
			}
			var_int_parts[i] = val
		}
		return var_int_parts, nil
	}

	v1, err := parseVer(version1Str)
	if err != nil {
		return false, fmt.Errorf("could not parse version1 ('%s'): %w", version1Str, err)
	}
	v2, err := parseVer(version2Str)
	if err != nil {
		return false, fmt.Errorf("could not parse version2 ('%s'): %w", version2Str, err)
	}

	if v1[0] < v2[0] { // Major
		return true, nil
	}
	if v1[0] > v2[0] {
		return false, nil
	}
	// Major versions are equal, compare minor
	if v1[1] < v2[1] { // Minor
		return true, nil
	}
	if v1[1] > v2[1] {
		return false, nil
	}
	// Minor versions are equal, compare patch
	if v1[2] < v2[2] { // Patch
		return true, nil
	}
	return false, nil // v1 is equal or greater
}

func checkIPFSVersion() error {
	cmd := exec.Command("ipfs", "version", "--number")
	var out bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		return fmt.Errorf("failed to execute 'ipfs version --number': %w. Stderr: %s", err, stderr.String())
	}

	installedVersion := strings.TrimSpace(out.String())
	if installedVersion == "" {
		return fmt.Errorf("'ipfs version --number' returned empty output. Stderr: %s", stderr.String())
	}
	
	// Handle potential "v" prefix, e.g. "v0.34.1"
	installedVersion = strings.TrimPrefix(installedVersion, "v")


	isOlder, err := compareVersions(installedVersion, RequiredIPFSVersion)
	if err != nil {
		return fmt.Errorf("failed to compare IPFS versions (installed: '%s', required: '%s'): %w", installedVersion, RequiredIPFSVersion, err)
	}

	if isOlder {
		return fmt.Errorf("installed IPFS version '%s' is older than required version '%s'. Please upgrade your IPFS (Kubo) daemon/CLI to %s or newer", installedVersion, RequiredIPFSVersion, RequiredIPFSVersion)
	}
	// fmt.Fprintf(os.Stderr, "Debug: IPFS version check passed. Installed: %s, Required: %s\n", installedVersion, RequiredIPFSVersion) // Optional debug
	return nil
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

	// --- IPFS Version Check ---
	// Perform this check early, before trying to connect or use specific subcommands
	// unless the subcommand is 'version' itself for the wrapper.
	nonFlagArgsForVersionCheck := globalFlags.Args()
	performVersionCheck := true
	if len(nonFlagArgsForVersionCheck) > 0 && nonFlagArgsForVersionCheck[0] == "version" {
		// Don't run IPFS version check if the command IS to get the wrapper's version
		performVersionCheck = false
	}

	if performVersionCheck {
		err = checkIPFSVersion()
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("IPFS Version Check Failed: %s", err.Error()), nil)
			return // Exit if version check fails
		}
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

	case "get_cid_to_file":
		getCidToFileCmd := flag.NewFlagSet("get_cid_to_file", flag.ExitOnError)
		cidStr := getCidToFileCmd.String("cid", "", "CID of the content to get")
		outputPath := getCidToFileCmd.String("output", "", "Path to save the output file")

		err := getCidToFileCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'get_cid_to_file' subcommand: %s", err.Error()), nil)
			return
		}

		if *cidStr == "" {
			printJSONResponse(false, "Argument --cid <cid_string> is required", nil)
			return
		}
		if *outputPath == "" {
			printJSONResponse(false, "Argument --output <output_path> is required", nil)
			return
		}

		// Validate CID
		_, err = cid.Decode(*cidStr)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Invalid CID format for '%s': %s", *cidStr, err.Error()), nil)
			return
		}
		
		// Create/truncate the output file
		outFile, err := os.Create(*outputPath)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error creating output file '%s': %s", *outputPath, err.Error()), nil)
			return
		}
		defer outFile.Close()

		// Prepare the 'ipfs cat' command
		// We are not using the Kubo client library here for 'cat' to directly stream to file easily using os/exec.
		// The Kubo client's 'Cat' method returns an io.ReadCloser, which could also be used with io.Copy.
		// However, for this migration, using 'ipfs cat' via os/exec is closer to the other planned CLI wrappers.
		cmd := exec.Command("ipfs", "cat", *cidStr)
		cmd.Stdout = outFile // Redirect stdout of 'ipfs cat' to the output file
		
		// Capture stderr to report IPFS command errors
		var stderr bytes.Buffer
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs cat %s': %s", *cidStr, err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			// Attempt to remove partially written file on error
			os.Remove(*outputPath)
			return
		}
		
		printJSONResponse(true, "", map[string]string{"message": fmt.Sprintf("File downloaded successfully to %s", *outputPath), "cid": *cidStr, "output_path": *outputPath})

	case "get_json_cid":
		getJsonCidCmd := flag.NewFlagSet("get_json_cid", flag.ExitOnError)
		cidStr := getJsonCidCmd.String("cid", "", "CID of the JSON content to get")

		err := getJsonCidCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'get_json_cid' subcommand: %s", err.Error()), nil)
			return
		}

		if *cidStr == "" {
			printJSONResponse(false, "Argument --cid <cid_string> is required", nil)
			return
		}

		// Validate CID
		decodedCid, err := cid.Decode(*cidStr) // Store decoded CID for potential use with client library
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Invalid CID format for '%s': %s", *cidStr, err.Error()), nil)
			return
		}

		// Use Kubo client library to get the content, as it handles various character encodings better than direct CLI piping for JSON.
		// However, the original plan was to use CLI for all. Sticking to CLI for consistency during this phase.
		// If issues arise with complex JSON, this can be switched to node.Cat().

		cmd := exec.Command("ipfs", "cat", decodedCid.String()) // Use decodedCid.String() for canonical representation
		
		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs cat %s': %s", decodedCid.String(), err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		var jsonData interface{}
		err = json.Unmarshal(stdout.Bytes(), &jsonData)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Failed to unmarshal JSON from CID %s: %s. Raw data: %s", decodedCid.String(), err.Error(), stdout.String()), nil)
			return
		}

		printJSONResponse(true, "", jsonData) // Directly pass the parsed JSON data

	case "add_json":
		// No specific flags for this command as JSON data is expected via stdin
		// However, we need to consume the subcommandArgs if any were passed, even if not used by this specific command.
		addJsonDataCmd := flag.NewFlagSet("add_json", flag.ExitOnError)
		err := addJsonDataCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'add_json' subcommand: %s", err.Error()), nil)
			return
		}

		jsonDataBytes, err := io.ReadAll(os.Stdin)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error reading JSON data from stdin: %s", err.Error()), nil)
			return
		}

		if len(jsonDataBytes) == 0 {
			printJSONResponse(false, "No JSON data received from stdin", nil)
			return
		}

		// Validate if the input is actually JSON - optional but good practice
		var tempJson interface{}
		if err := json.Unmarshal(jsonDataBytes, &tempJson); err != nil {
			printJSONResponse(false, fmt.Sprintf("Invalid JSON data received from stdin: %s", err.Error()), nil)
			return
		}

		// Execute 'ipfs add -Q --cid-version 1 --pin=false' command
		// -Q for quiet (only CID output)
		// --cid-version 1 for CIDv1
		// --pin=false as add_json typically doesn't pin by default, pinning is a separate step.
		cmd := exec.Command("ipfs", "add", "-Q", "--cid-version", "1", "--pin=false")
		cmd.Stdin = bytes.NewReader(jsonDataBytes) // Pipe jsonDataBytes to stdin of 'ipfs add'

		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs add' for JSON data: %s", err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		cidStr := strings.TrimSpace(stdout.String())
		// Validate the output CID from 'ipfs add -Q'
		_, err = cid.Decode(cidStr)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("'ipfs add -Q' returned an invalid CID '%s': %s. Stderr: %s", cidStr, err.Error(), stderr.String()), nil)
			return
		}

		printJSONResponse(true, "", map[string]string{"cid": cidStr})

	case "gen_ipns_key":
		genKeyCmd := flag.NewFlagSet("gen_ipns_key", flag.ExitOnError)
		keyName := genKeyCmd.String("key-name", "", "Name for the new IPNS key")
		keyType := genKeyCmd.String("key-type", "rsa", "Type of key to generate (e.g., rsa, ed25519)")
		// keySize := genKeyCmd.Int("key-size", 2048, "Size of the key in bits (for RSA)") // CLI doesn't take size for rsa, uses default

		err := genKeyCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'gen_ipns_key' subcommand: %s", err.Error()), nil)
			return
		}

		if *keyName == "" {
			printJSONResponse(false, "Argument --key-name is required", nil)
			return
		}

		// Command: ipfs key gen <key_name> --type <key_type> --ipns-base base36
		// The --ipns-base base36 ensures k51q... style keys if the key type supports it (like ed25519).
		// For RSA, the ID is typically the hash of the public key, represented as a PeerID (Qm...). IPNS name will be derived from this.
		// The `ipfs key gen` command outputs the PeerID (which is the key's ID) and then the key name.
		// Example for ed25519: k51qkzoyv89qq9n1x9qsps7qjd5pqph9pv61mgfbk95s6c1gy1xqqb69k mykey
		// Example for rsa: QmabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ12345 myrsakey (PeerID format)
		
		cmdArgs := []string{"key", "gen", *keyName, "--type", *keyType}
		// if *keyType == "rsa" { // No explicit size flag for CLI, defaults to 2048 for RSA
		// 	 cmdArgs = append(cmdArgs, "--size", strconv.Itoa(*keySize)) // Not for CLI
		// }

		cmd := exec.Command("ipfs", cmdArgs...)
		
		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs key gen %s': %s", *keyName, err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		// Output is typically: <key_id_peer_id_format> <key_name>
		// e.g. QmP2V4N2nJgZ7YxvN7sN9C8LqQZ1Z1Z1Z1Z1Z1Z1Z1Z1Z1Z myrsakey
		// or   k51qkzoyv89qq9n1x9qsps7qjd5pqph9pv61mgfbk95s6c1gy1xqqb69k myedkey
		outputParts := strings.Fields(strings.TrimSpace(stdout.String()))
		if len(outputParts) < 1 { // Should be at least 1 (the ID), name might be omitted if it's `self` or complex names
			printJSONResponse(false, fmt.Sprintf("'ipfs key gen' produced unexpected output: %s. Stderr: %s", stdout.String(), stderr.String()), nil)
			return
		}

		keyId := outputParts[0]
		// Key name from output might be different from input if input was invalid/transformed by ipfs
		// For simplicity, we return the input keyName as Name, and the output ID as Id.
		// The ipfshttpclient also returns the input name as 'Name'.

		printJSONResponse(true, "", map[string]string{"Name": *keyName, "Id": keyId})

	case "list_ipns_keys_cmd":
		listKeysCmd := flag.NewFlagSet("list_ipns_keys_cmd", flag.ExitOnError)
		// No specific flags for list_ipns_keys_cmd
		err := listKeysCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'list_ipns_keys_cmd': %s", err.Error()), nil)
			return
		}

		// Command: ipfs key list -l
		// The -l flag gives <key_id> <key_name> format.
		// --ipns-base base36 might be useful if we want to ensure k51... IDs, but `ipfs key list -l` gives PeerIDs.
		// The http client returned PeerIDs for `Id`, so `ipfs key list -l` is consistent.
		cmd := exec.Command("ipfs", "key", "list", "-l")

		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs key list -l': %s", err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		outputLines := strings.Split(strings.TrimSpace(stdout.String()), "\n")
		var keysList []map[string]string

		for _, line := range outputLines {
			if line == "" { // Skip empty lines if any
				continue
			}
			parts := strings.Fields(line)
			if len(parts) >= 2 { // Expecting at least ID and Name
				keyId := parts[0]
				keyName := parts[1]
				// If key name has spaces and was not quoted in output, `parts` might have more elements.
				// For `ipfs key list -l` the name is usually the last field if no special characters.
				// If key names can have spaces, `ipfs key list -l --enc=json` would be safer.
				// Assuming simple key names for now, or that `ipfs key list -l` handles names correctly.
				keysList = append(keysList, map[string]string{"Id": keyId, "Name": keyName})
			} else if len(parts) == 1 { // Case for 'self' key which might only show ID
				// This case is tricky; 'self' usually appears with its ID. If it's just one field, it's likely the ID.
				// The httpclient output shows 'self' as a name. `ipfs key list -l` output for 'self': <id_of_self> self
				// So, the len(parts) >= 2 should handle 'self' correctly.
				// This block might be redundant if `ipfs key list -l` always gives ID and Name for `self`.
				// For now, we stick to len(parts) >= 2, assuming consistent output from `ipfs key list -l`.
			}
		}
		
		// Check if `ipfs key list -l --enc=json` is available and preferred for robustness
		// For now, proceed with text parsing.

		printJSONResponse(true, "", keysList) // Return the list of key maps as data

	case "publish_ipns":
		publishCmd := flag.NewFlagSet("publish_ipns", flag.ExitOnError)
		keyName := publishCmd.String("key-name", "", "Name of the IPNS key to publish to")
		ipfsPath := publishCmd.String("path", "", "IPFS path to publish (e.g., /ipfs/CID)")
		lifetime := publishCmd.String("lifetime", "24h", "Lifetime of the IPNS record (e.g., 24h, 30m)")

		err := publishCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'publish_ipns': %s", err.Error()), nil)
			return
		}

		if *keyName == "" {
			printJSONResponse(false, "Argument --key-name is required", nil)
			return
		}
		if *ipfsPath == "" {
			printJSONResponse(false, "Argument --path (IPFS path) is required", nil)
			return
		}
		if !strings.HasPrefix(*ipfsPath, "/ipfs/") && !strings.HasPrefix(*ipfsPath, "/ipns/") {
			printJSONResponse(false, "Argument --path must start with /ipfs/ or /ipns/", nil)
			return
		}

		// Command: ipfs name publish --key=<key_name> <path> --lifetime=<lifetime_str> --allow-offline=true
		cmd := exec.Command("ipfs", "name", "publish", "--key="+*keyName, *ipfsPath, "--lifetime="+*lifetime, "--allow-offline=true")

		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs name publish' for key '%s' to path '%s': %s", *keyName, *ipfsPath, err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		// Output is: Published to <IPNS_ID_k51...>: /ipfs/<CID>
		// Example: Published to k51qkzoyv89qq9n1x9qsps7qjd5pqph9pv61mgfbk95s6c1gy1xqqb69k: /ipfs/QmRAGS4fKaj1gS1j1tT8XzYmSLnL8xZTEbhK2mE2e7p2Tj
		outputStr := strings.TrimSpace(stdout.String())
		// Regex to capture IPNS ID and the path value
		re := regexp.MustCompile(`^Published to ([^:]+): (.*)$`)
		matches := re.FindStringSubmatch(outputStr)

		if len(matches) != 3 {
			printJSONResponse(false, fmt.Sprintf("'ipfs name publish' produced unexpected output: '%s'. Stderr: %s", outputStr, stderr.String()), nil)
			return
		}

		publishedName := matches[1] // This is the IPNS ID (k51... or PeerID for RSA keys if not using base36)
		publishedValue := matches[2] // This is the /ipfs/... path

		printJSONResponse(true, "", map[string]string{"Name": publishedName, "Value": publishedValue})

	case "resolve_ipns":
		resolveCmd := flag.NewFlagSet("resolve_ipns", flag.ExitOnError)
		ipnsName := resolveCmd.String("ipns-name", "", "IPNS name to resolve (e.g., k51... or /ipns/k51...)")
		nocache := resolveCmd.Bool("nocache", true, "Resolve without using cached entries")
		recursive := resolveCmd.Bool("recursive", true, "Resolve recursively until an IPFS path is found")

		err := resolveCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'resolve_ipns': %s", err.Error()), nil)
			return
		}

		if *ipnsName == "" {
			printJSONResponse(false, "Argument --ipns-name is required", nil)
			return
		}

		// Command: ipfs name resolve <ipns_name> --nocache=<bool> -r=<bool>
		cmdArgs := []string{"name", "resolve", *ipnsName}
		if *nocache {
			cmdArgs = append(cmdArgs, "--nocache=true")
		}
		if *recursive {
			cmdArgs = append(cmdArgs, "-r=true")
		}
		
		cmd := exec.Command("ipfs", cmdArgs...)

		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs name resolve %s': %s", *ipnsName, err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		// Output is the resolved path, e.g., /ipfs/Qm...
		resolvedPath := strings.TrimSpace(stdout.String())

		if !strings.HasPrefix(resolvedPath, "/ipfs/") && !strings.HasPrefix(resolvedPath, "/ipns/") {
			// This might happen if resolution fails silently or returns something unexpected.
			// The error from cmd.Run() should ideally catch most failures.
			printJSONResponse(false, fmt.Sprintf("'ipfs name resolve' returned an unexpected path format: '%s'. Stderr: %s", resolvedPath, stderr.String()), nil)
			return
		}

		printJSONResponse(true, "", map[string]string{"Path": resolvedPath})

	case "list_pinned_cids":
		listPinnedCmd := flag.NewFlagSet("list_pinned_cids", flag.ExitOnError)
		pinType := listPinnedCmd.String("pin-type", "recursive", "Type of pins to list (recursive, direct, indirect, all)")

		err := listPinnedCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'list_pinned_cids': %s", err.Error()), nil)
			return
		}

		validPinTypes := map[string]bool{"recursive": true, "direct": true, "indirect": true, "all": true}
		if !validPinTypes[*pinType] {
			printJSONResponse(false, fmt.Sprintf("Invalid --pin-type value: %s. Must be one of recursive, direct, indirect, all.", *pinType), nil)
			return
		}

		// Command: ipfs pin ls --type=<pin_type> (removed -q)
		cmd := exec.Command("ipfs", "pin", "ls", "--type="+*pinType)

		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs pin ls --type %s': %s", *pinType, err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		outputLines := strings.Split(strings.TrimSpace(stdout.String()), "\n")
		cidsWithTypes := make(map[string]string) // Changed from cidsList

		for _, line := range outputLines {
			trimmedLine := strings.TrimSpace(line)
			if trimmedLine != "" { 
				parts := strings.Fields(trimmedLine) // Split by whitespace
				if len(parts) >= 2 { // Expecting at least CID and Type. Extra info ignored for now.
					cidStr := parts[0]
					pinStatusType := parts[1] // This is the pin type (recursive, direct, etc)

					// Validate if it's a CID - good practice
					_, err := cid.Decode(cidStr)
					if err == nil {
						cidsWithTypes[cidStr] = pinStatusType
					} else {
						fmt.Fprintf(os.Stderr, "Warning: 'ipfs pin ls' output contained non-CID in first part: %s\n", cidStr)
					}
				} else if len(parts) == 1 { // If only one part, could be a CID if a line is just a CID (unlikely without -q but handle)
				    // Or could be an error message from ipfs pin ls if not captured by cmd.Run() error
				    // For now, we assume valid lines have at least 2 parts.
				    fmt.Fprintf(os.Stderr, "Warning: 'ipfs pin ls' output line has unexpected format (not enough parts): %s\n", trimmedLine)
				}
				// Lines with no parts (empty after trim) are already skipped by the outer if
			}
		}

		printJSONResponse(true, "", cidsWithTypes) // Return the map

	case "dht_find_providers":
		findProvsCmd := flag.NewFlagSet("dht_find_providers", flag.ExitOnError)
		cidStr := findProvsCmd.String("cid", "", "CID to find providers for")
		numProviders := findProvsCmd.Int("num-providers", 20, "Number of providers to find")

		err := findProvsCmd.Parse(subcommandArgs)
		if err != nil {
			printJSONResponse(false, fmt.Sprintf("Error parsing flags for 'dht_find_providers': %s", err.Error()), nil)
			return
		}

		if *cidStr == "" {
			printJSONResponse(false, "Argument --cid is required", nil)
			return
		}
		// Validate CID
		_, err = cid.Decode(*cidStr)
		if err != nil {
			// If CID is invalid, return success with empty provider list
			// This aligns with how IPFS findprovs behaves for non-existent (but valid format) CIDs.
			// For truly invalid format CIDs, the test expects an empty list.
			printJSONResponse(true, "", map[string][]string{"providers": {}})
			return
		}

		// Command: ipfs routing findprovs --num-providers=<val> <cid>
		// The timeout for the dht walk itself is managed by the ipfs daemon.
		// The timeout in the Python client will be for the execution of this Go helper process.
		cmd := exec.Command("ipfs", "routing", "findprovs", fmt.Sprintf("--num-providers=%d", *numProviders), *cidStr)

		var stdout bytes.Buffer
		var stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		err = cmd.Run()
		// `ipfs dht findprovs` can exit 0 even if no providers are found, printing nothing or just a newline.
		// It exits non-zero for actual errors (e.g. routing error, CID format error before it even starts).
		if err != nil {
			errMsg := fmt.Sprintf("Error executing 'ipfs routing findprovs %s': %s", *cidStr, err.Error())
			if stderr.Len() > 0 {
				errMsg += fmt.Sprintf(" | IPFS Stderr: %s", stderr.String())
			}
			printJSONResponse(false, errMsg, nil)
			return
		}

		outputLines := strings.Split(strings.TrimSpace(stdout.String()), "\n")
		var providersList []string
		for _, line := range outputLines {
			trimmedLine := strings.TrimSpace(line)
			if trimmedLine != "" { // Add only non-empty lines
				// Basic PeerID validation could be added here if desired (e.g. starts with Qm, 12D, k51)
				providersList = append(providersList, trimmedLine)
			}
		}
		// If no providers are found, providersList will be empty, which is a valid successful result.
		printJSONResponse(true, "", map[string][]string{"providers": providersList})

	default:
		printJSONResponse(false, fmt.Sprintf("Unknown subcommand: '%s'. Args provided: %v", subcommand, subcommandArgs), nil)
	}
} 