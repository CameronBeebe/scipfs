import logging
from pathlib import Path
from typing import Dict, Optional, List, Set, Tuple
import json
import subprocess # Import subprocess
import re # For version parsing in check_ipfs_daemon

# Configure logging
# logging.basicConfig(level=logging.INFO) # Removed: logging is configured at application level in cli.py
logger = logging.getLogger(__name__)

# Custom Exceptions
class SciPFSException(Exception):
    """Base exception for scipfs client errors."""
    pass

class IPFSConnectionError(SciPFSException): # Renamed ConnectionError to IPFSConnectionError for clarity
    """Raised for errors connecting to IPFS or the Go wrapper."""
    pass

class KuboVersionError(SciPFSException): # Added KuboVersionError
    """Raised when the connected IPFS Kubo daemon version is incompatible."""
    pass

class RuntimeError(SciPFSException):
    """Raised for general runtime errors during IPFS operations via Go wrapper."""
    pass

class TimeoutError(SciPFSException):
    """Raised when an IPFS operation times out."""
    pass

class SciPFSGoWrapperError(SciPFSException):
    """Raised for errors specific to the Go wrapper interactions."""
    pass

class SciPFSFileNotFoundError(SciPFSException, OSError):
    """Raised when a local file to be added is not found."""
    pass


class IPFSClient:
    """Manages interactions with an IPFS node using the scipfs_go_helper.
    All IPFS operations are now routed through a local Go executable.
    """
    
    def __init__(self, api_addr: str = "/ip4/127.0.0.1/tcp/5001", required_version_tuple: Optional[Tuple[int, int, int]] = None):
        """Initialize IPFS client. 
        Actual checks for wrapper and daemon are deferred to check_ipfs_daemon().

        Args:
            api_addr: The multiaddress of the IPFS API.
            required_version_tuple: Minimum required Kubo version (e.g., (0, 23, 0)).
        """
        self.api_addr = api_addr
        self.required_version_tuple = required_version_tuple
        self.go_wrapper_executable_name = "scipfs_go_helper" 
        self.go_wrapper_path: Optional[str] = None
        self.go_wrapper_version: Optional[str] = None
        self.go_wrapper_error: Optional[str] = None 
        self.client_id_dict: Optional[Dict] = None # To store Peer ID info
        self.daemon_version_str: Optional[str] = None # To store daemon version string
        self.client: Optional[object] = None # ipfshttpclient.Client is no longer used.

        # Try to find the Go wrapper executable immediately
        self._find_go_wrapper()
        
    def _find_go_wrapper(self) -> None:
        """Tries to find the Go wrapper executable and get its version."""
        possible_paths = [
            f"./{self.go_wrapper_executable_name}",  # Check current directory
            str(Path(__file__).parent.parent / self.go_wrapper_executable_name), # Check alongside package
            self.go_wrapper_executable_name          # Check PATH
        ]
        found_wrapper = False
        for path_attempt in possible_paths:
            try:
                # The version command in go_helper should not require api_addr
                cmd = [path_attempt, "version"]
                logger.debug(f"Attempting to find Go wrapper at: {path_attempt}")
                result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
                
                if result.returncode == 0:
                    try:
                        response_json = json.loads(result.stdout)
                        if response_json.get("success") and "version" in response_json.get("data", {}):
                            self.go_wrapper_path = path_attempt
                            self.go_wrapper_version = response_json["data"]["version"]
                            logger.info(
                                f"Successfully found SciPFS Go Helper version {self.go_wrapper_version} at '{self.go_wrapper_path}'."
                            )
                            found_wrapper = True
                            break  # Found and verified
                        else:
                            logger.debug(
                                f"Go wrapper at '{path_attempt}' ran but gave unexpected version output: {result.stdout.strip()}"
                            )
                    except json.JSONDecodeError:
                        logger.debug(
                            f"Go wrapper at '{path_attempt}' ran but gave non-JSON output for version: {result.stdout.strip()}"
                        )
                else:
                     logger.debug(f"Go wrapper version command at '{path_attempt}' failed. stderr: {result.stderr.strip() if result.stderr else 'Unknown error'}")
            except FileNotFoundError:
                logger.debug(f"Go wrapper not found at '{path_attempt}'.")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout checking Go wrapper at '{path_attempt}' with version command.")
            except Exception as e: 
                logger.error(f"Unexpected error checking Go wrapper at '{path_attempt}': {e}")

        if not found_wrapper:
            self.go_wrapper_error = f"SciPFS Go Helper ('{self.go_wrapper_executable_name}') not found or non-functional. Checked: {possible_paths}. Please ensure it is built and in your PATH or project directory."
            logger.error(self.go_wrapper_error)
            # Do not raise here, let check_ipfs_daemon handle it as it might be called by commands that don't need IPFS.

    def check_ipfs_daemon(self) -> None:
        """Checks Go wrapper, IPFS daemon connectivity, and version.
        Raises IPFSConnectionError or KuboVersionError on failure.
        This should be called by CLI commands that require IPFS interaction.
        """
        if not self.is_go_wrapper_available():
            # self.go_wrapper_error would have been set by _find_go_wrapper if it failed
            raise IPFSConnectionError(self.go_wrapper_error or f"SciPFS Go Helper ('{self.go_wrapper_executable_name}') is not available.")

        try:
            logger.debug(f"Attempting to get daemon info via Go wrapper from API: {self.api_addr}")
            daemon_info = self.get_daemon_info() # This uses _execute_go_wrapper_command_json
            
            if not daemon_info:
                # get_daemon_info should raise SciPFSGoWrapperError if the command failed in a way that returns None early.
                # If it returns None without raising, it implies a non-error empty response, which is odd.
                err_msg = f"Failed to get daemon info from IPFS node at {self.api_addr}. Response was empty or invalid."
                logger.error(err_msg)
                raise IPFSConnectionError(err_msg)

            self.client_id_dict = daemon_info # Store the full daemon info if needed
            self.daemon_version_str = daemon_info.get("Version") # Kubo typically has "Version" e.g. "0.23.0"
            if not self.daemon_version_str:
                # Some IPFS versions might use AgentVersion (e.g. "kubo/0.13.0/...")
                agent_version = daemon_info.get("AgentVersion", "")
                if "kubo/" in agent_version:
                    self.daemon_version_str = agent_version.split('/')[1]
            
            if not self.daemon_version_str:
                err_msg = f"Could not determine IPFS daemon version from API {self.api_addr}. Response: {daemon_info}"
                logger.error(err_msg)
                raise IPFSConnectionError(err_msg)

            logger.info(f"Successfully connected to IPFS node. Peer ID: {daemon_info.get('ID')}, Version: {self.daemon_version_str}")

            # Perform version check if required_version_tuple is set
            if self.required_version_tuple:
                if not self.check_version(self.required_version_tuple):
                    # check_version logs the details
                    raise KuboVersionError(
                        f"IPFS daemon version '{self.daemon_version_str}' is not compatible. "
                        f"Required: {self.required_version_tuple[0]}.{self.required_version_tuple[1]}.{self.required_version_tuple[2]}+"
                    )
            logger.info(f"IPFS daemon version '{self.daemon_version_str}' is compatible or not checked against requirement.")

        except SciPFSGoWrapperError as e: # Errors from _execute_go_wrapper_command_json (e.g. timeout, process error, bad JSON)
            # Check if the error message indicates connection refused, which is a common scenario
            if "connection refused" in str(e).lower() or "context deadline exceeded" in str(e).lower() and "daemon_info" in str(e).lower():
                err_msg = f"Could not connect to IPFS API at {self.api_addr}. Ensure IPFS daemon is running. Details: {e}"
            else:
                err_msg = f"Error communicating with IPFS daemon via Go wrapper at {self.api_addr}: {e}"
            logger.error(err_msg)
            raise IPFSConnectionError(err_msg) from e
        except SciPFSException as e: # Catch our own specific exceptions first
            logger.warning(f"SciPFS-specific exception during IPFS daemon check: {e}")
            raise # Re-raise SciPFSException and its children (like KuboVersionError)
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"Unexpected error during IPFS daemon check for {self.api_addr}: {e}", exc_info=True)
            raise IPFSConnectionError(f"Unexpected error during IPFS daemon check: {e}") from e

    def check_version(self, required_tuple: Tuple[int, int, int]) -> bool:
        """Compares the daemon version string (self.daemon_version_str) against a required tuple."""
        if not self.daemon_version_str:
            logger.warning("Cannot check version, daemon version string is not set.")
            return False # Cannot confirm, assume not met
        
        match = re.search(r'^(\d+)\.(\d+)\.(\d+)', self.daemon_version_str)
        if not match:
            logger.warning(f"Could not parse daemon version string: '{self.daemon_version_str}' for comparison.")
            return False # Cannot parse, assume not met

        actual_tuple = tuple(map(int, match.groups()))
        
        if actual_tuple >= required_tuple:
            logger.debug(f"IPFS version check: Actual {actual_tuple} >= Required {required_tuple} (OK)")
            return True
        else:
            logger.warning(
                f"IPFS version check: Actual {actual_tuple} < Required {required_tuple} (FAIL). "
                f"Daemon version: '{self.daemon_version_str}', Required: '{required_tuple[0]}.{required_tuple[1]}.{required_tuple[2]}+'"
            )
            return False

    def get_version_str(self) -> Optional[str]:
        """Returns the detected daemon version string."""
        return self.daemon_version_str

    def is_go_wrapper_available(self) -> bool:
        """Check if the Go wrapper was successfully found and its version obtained."""
        return bool(self.go_wrapper_path and self.go_wrapper_version)

    def add_file(self, file_path: Path, pin: bool = True) -> str: # Added pin argument
        """Add a file to IPFS using the Go wrapper and return its CID."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for add_file."
            logger.error(error_msg)
            raise IPFSConnectionError(f"Cannot add file: {error_msg}")

        if not file_path.is_file():
            raise SciPFSFileNotFoundError(f"File not found: {file_path}")

        command_args = [
            "add_file",
            "--file", str(file_path)
        ]
        if not pin: # go_helper add_file defaults to pinning, so only add --pin=false if we don't want to pin
            command_args.extend(["--pin", "false"]) 

        try:
            logger.debug(f"Executing Go wrapper command for add_file: {self.go_wrapper_path} {' '.join(command_args)}")
            response_data = self._execute_go_wrapper_command_json(*command_args, timeout_seconds=300) # 5 min timeout
            
            cid = response_data.get("cid")
            if cid:
                logger.info(f"Successfully added file '{file_path}' via Go wrapper. CID: {cid}, Pinned: {pin}")
                return cid
            else:
                error_msg = "CID not found in successful response from Go wrapper's add_file"
                logger.error(f"Go wrapper's add_file command for '{file_path}' seemed to succeed but no CID was returned: {response_data}")
                raise RuntimeError(error_msg)

        except SciPFSGoWrapperError as e: # Catch errors from _execute_go_wrapper_command_json
            logger.error(f"Go wrapper add_file command failed for '{file_path}': {e}")
            raise RuntimeError(f"Go wrapper command for add_file '{file_path}' failed: {e}") from e # Chain exception
        except SciPFSFileNotFoundError: # This will catch our custom one now if file_path itself is the issue
            logger.error(f"File '{file_path}' not found for add_file operation.")
            raise # Re-raise the FileNotFoundError
        except TimeoutError as e: # Catch specifically TimeoutError from _execute_go_wrapper_command_json
            logger.error(f"Timeout during 'add_file' command with Go wrapper for '{file_path}'. Details: {e}")
            raise # Re-raise
        except Exception as e:
            logger.error(f"An unexpected error occurred calling Go wrapper for add_file '{file_path}': {e}", exc_info=True)
            if isinstance(e, SciPFSException):
                raise 
            raise RuntimeError(f"Unexpected error adding file '{file_path}' with Go wrapper: {str(e)}") from e

    def get_file(self, cid: str, output_path: Path) -> None:
        """Download a file from IPFS by CID to the specified path using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for get_file."
            logger.error(error_msg)
            raise IPFSConnectionError(f"Cannot get file: {error_msg}")

        args = ["--cid", cid, "--output", str(output_path)]
        try:
            # We expect a success message, not necessarily data in the 'data' field of the JSON response.
            # The _execute_go_wrapper_command_json checks for overall success.
            # If it returns without error, the Go wrapper handled the file download.
            self._execute_go_wrapper_command_json("get_cid_to_file", *args)
            logger.info(f"Successfully instructed Go wrapper to download CID {cid} to {output_path}")
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper command 'get_cid_to_file' failed for CID {cid} to {output_path}: {e}")
            # SciPFSGoWrapperError is already specific enough.
            # Potentially, os.remove(output_path) if the Go wrapper didn't clean up a partial file on its error.
            # However, the Go side now attempts os.Remove on its error.
            raise
        except TimeoutError as e: # Catch specifically TimeoutError from _execute_go_wrapper_command_json
            logger.error(f"Timeout during 'get_file' command with Go wrapper for CID {cid}. Details: {e}")
            raise # Re-raise
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for get_file (CID {cid}, Output {output_path}): {e}")
            if isinstance(e, SciPFSException):
                raise # Re-raise if it's already one of ours
            raise RuntimeError(f"Unexpected error during get_file via Go wrapper for CID {cid}: {str(e)}")

    def pin(self, cid: str) -> None:
        """Pin a CID to ensure it remains available using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available."
            logger.error(f"Cannot pin CID {cid}: {error_msg}")
            raise IPFSConnectionError(f"Cannot pin: {error_msg}")

        try:
            logger.debug(f"Executing Go wrapper command for pin: {self.go_wrapper_path} pin {cid}")
            # Expects success, no specific data needed from response beyond that.
            self._execute_go_wrapper_command_json("pin", cid, timeout_seconds=90)
            logger.info(f"Successfully pinned CID {cid} via Go wrapper.")
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper failed to pin CID {cid}: {e}")
            raise RuntimeError(f"Go wrapper failed to pin CID {cid}: {e}") from e
        except TimeoutError as e:
            logger.error(f"Timeout pinning CID {cid} via Go wrapper: {e}")
            raise # Re-raise
        except Exception as e:
            logger.error(f"An unexpected error occurred calling Go wrapper for pin CID {cid}: {e}", exc_info=True)
            if isinstance(e, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error pinning CID {cid} with Go wrapper: {str(e)}") from e

    def unpin(self, cid: str) -> None:
        """Unpin a CID using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for unpin."
            logger.error(error_msg)
            raise IPFSConnectionError(f"Cannot unpin CID: {error_msg}")

        try:
            logger.debug(f"Executing Go wrapper command for unpin: {self.go_wrapper_path} unpin {cid}")
            self._execute_go_wrapper_command_json("unpin", cid, timeout_seconds=90)
            logger.info(f"Successfully unpinned CID {cid} via Go wrapper.")
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper failed to unpin CID {cid}: {e}")
            raise RuntimeError(f"Go wrapper failed to unpin CID {cid}: {e}") from e
        except TimeoutError as e:
            logger.error(f"Timeout unpinning CID {cid} via Go wrapper: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred calling Go wrapper for unpin CID {cid}: {e}", exc_info=True)
            if isinstance(e, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error unpinning CID {cid} with Go wrapper: {str(e)}") from e

    def get_json(self, cid: str) -> Dict:
        """Retrieve and parse JSON content from IPFS by CID using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for get_json."
            logger.error(error_msg)
            raise IPFSConnectionError(f"Cannot get JSON: {error_msg}")

        try:
            # _execute_go_wrapper_command_json should return the "data" part of the successful JSON response
            json_data = self._execute_go_wrapper_command_json("get_json_cid", "--cid", cid)
            if not isinstance(json_data, Dict): # Check if it's a dictionary before returning
                logger.error(f"Go wrapper returned non-dict data for get_json_cid (CID: {cid}). Type: {type(json_data)}. Data: {json_data}")
                raise SciPFSGoWrapperError(f"Go wrapper returned non-dictionary data for JSON content (CID: {cid}). Got: {json_data}")
            logger.info(f"Successfully retrieved JSON for CID {cid} via Go wrapper.")
            return json_data
        except SciPFSGoWrapperError as e:
            logger.error(f"SciPFSGoWrapperError during get_json for CID {cid}: {e}")
            raise # Re-raise the SciPFSGoWrapperError as expected by tests
        except IPFSConnectionError: # Catch and re-raise if it was an IPFSConnectionError
            raise
        except TimeoutError as e: # Catch and re-raise our custom TimeoutError
            logger.error(f"Timeout during get_json for CID {cid}: {e}")
            raise
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"Unexpected error in get_json for CID {cid}: {e}", exc_info=True)
            # Wrap unexpected errors in a SciPFSException for consistent error hierarchy
            raise SciPFSException(f"Unexpected error retrieving JSON for CID {cid}: {e}") from e

    def add_json(self, data: Dict) -> str:
        """Add a JSON serializable dictionary to IPFS and return its CID."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for add_json."
            logger.error(error_msg)
            raise IPFSConnectionError(f"Cannot add_json: {error_msg}")
        
        try:
            json_string = json.dumps(data)
            # The Go helper's 'add_json' (formerly 'add_json_data') command now expects JSON via stdin.
            response_data = self._execute_go_wrapper_command_json("add_json", input_data=json_string, timeout_seconds=60)
            cid = response_data.get("cid")
            if cid:
                logger.info(f"Successfully added JSON via Go wrapper (stdin). CID: {cid}")
                return cid
            else:
                logger.error(f"CID not found in Go wrapper response for add_json: {response_data}")
                raise RuntimeError("CID not found in Go wrapper response for add_json")
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper add_json failed: {e}")
            raise RuntimeError(f"Go wrapper add_json failed: {e}") from e
        except TimeoutError as e:
            logger.error(f"Timeout adding JSON via Go wrapper: {e}")
            raise
        except json.JSONDecodeError as e_json: # Should not happen if Go wrapper returns valid JSON success/error
            logger.error(f"Internal error: Failed to serialize data for add_json: {e_json}")
            raise RuntimeError(f"Internal error: Failed to serialize data for add_json: {e_json}") from e_json
        except Exception as e:
            logger.error(f"An unexpected error calling Go wrapper for add_json: {e}", exc_info=True)
            if isinstance(e, SciPFSException):
                raise # Re-raise if it's already one of ours
            raise RuntimeError(f"Unexpected error during add_json via Go wrapper: {str(e)}")

    def generate_ipns_key(self, key_name: str) -> Dict:
        """Generate a new IPNS key with the given name using the Go wrapper.
        Returns a dictionary with key details (e.g., {"Name": "key_name", "Id": "peer_id"}).
        """
        if not self.is_go_wrapper_available():
            raise IPFSConnectionError(self.go_wrapper_error or "Go wrapper not available for generate_ipns_key.")

        try:
            # _execute_go_wrapper_command_json will return the "data" part of the Go helper's response.
            # The Go helper for 'gen_key' should return {"success": true, "data": {"Name": "name", "Id": "id"}}
            # Flag name based on Go wrapper output: -key-name
            key_info = self._execute_go_wrapper_command_json("gen_ipns_key", "-key-name", key_name)
            if key_info and "Name" in key_info and "Id" in key_info:
                logger.info(f"Successfully generated IPNS key '{key_name}' with ID '{key_info['Id']}' via Go wrapper.")
                return key_info
            else:
                logger.error(f"IPNS key generation for '{key_name}' via Go wrapper returned unexpected data: {key_info}")
                raise RuntimeError(f"IPNS key generation for '{key_name}' returned unexpected data.")
        except SciPFSGoWrapperError as e:
            # Check if the error indicates the key already exists
            if "key already exists" in str(e).lower() or ("already exists" in str(e).lower() and "name" in str(e).lower() and key_name in str(e).lower()): # More robust check
                logger.warning(f"IPNS key '{key_name}' already exists. Attempting to retrieve and return existing key. Error: {e}")
                # If key already exists, try to list it to get its ID
                # This is a common pattern: if generation fails due to existence, return the existing one.
                try:
                    existing_keys = self.list_ipns_keys()
                    for key in existing_keys:
                        if key.get("Name") == key_name:
                            logger.info(f"Returning existing IPNS key '{key_name}' with ID '{key['Id']}'.")
                            return key # Return the existing key data
                    # If not found in list (should not happen if "already exists" was the error from gen_ipns_key)
                    logger.error(f"IPNS key '{key_name}' reported as existing by gen_ipns_key, but not found in list_ipns_keys.")
                    raise RuntimeError(f"IPNS key '{key_name}' generation failed, and existing key could not be retrieved.") from e
                except SciPFSException as list_e: # Catch SciPFSException from list_ipns_keys
                    logger.error(f"Failed to list IPNS keys to retrieve existing key '{key_name}' after gen_ipns_key reported it exists: {list_e}")
                    raise RuntimeError(f"IPNS key '{key_name}' generation reported it exists, but failed to retrieve it.") from list_e
            
            logger.error(f"Go wrapper failed to generate IPNS key '{key_name}': {e}")
            raise RuntimeError(f"Go wrapper failed to generate IPNS key '{key_name}': {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during IPNS key generation for '{key_name}': {e}", exc_info=True)
            if isinstance(e, SciPFSException): # Re-raise if it's already one of our specific exceptions
                raise
            raise RuntimeError(f"Unexpected error generating IPNS key '{key_name}': {str(e)}") from e

    def list_ipns_keys(self) -> List[Dict]:
        """List all IPNS keys known to the IPFS node using the Go wrapper.
        Returns a list of dictionaries, where each dict contains key details (e.g., {"Name": "key_name", "Id": "peer_id"}).
        """
        if not self.is_go_wrapper_available():
            raise IPFSConnectionError(self.go_wrapper_error or "Go wrapper not available for list_ipns_keys.")

        try:
            # The Go helper for 'list_keys' should return {"success": true, "data": [{"Name": "name1", "Id": "id1"}, ...]}
            # Based on grep, the command is "list_ipns_keys_cmd"
            keys_data = self._execute_go_wrapper_command_json("list_ipns_keys_cmd") # Empty args
            
            if isinstance(keys_data, list): # Expecting a list of key objects
                logger.info(f"Successfully listed {len(keys_data)} IPNS keys via Go wrapper.")
                return keys_data
            elif keys_data is None: # Handle case where 'data' might be null or missing for an empty list scenario
                 logger.info("No IPNS keys found or Go wrapper returned null for data.")
                 return [] # Return empty list if data is None
            else:
                logger.error(f"IPNS key list via Go wrapper returned unexpected data type: {type(keys_data)}, data: {keys_data}")
                raise RuntimeError(f"IPNS key list returned unexpected data type: {type(keys_data)}")
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper failed to list IPNS keys: {e}")
            raise RuntimeError(f"Go wrapper failed to list IPNS keys: {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during listing IPNS keys: {e}", exc_info=True)
            if isinstance(e, SciPFSException): # Re-raise if it's already one of our specific exceptions
                raise
            raise RuntimeError(f"Unexpected error listing IPNS keys: {str(e)}") from e

    def check_key_exists(self, key_name: str) -> bool:
        """Check if an IPNS key with the given name exists."""
        if not self.is_go_wrapper_available():
            raise IPFSConnectionError(self.go_wrapper_error or "Go wrapper not available for check_key_exists.")
        try:
            all_keys = self.list_ipns_keys()
            for key_info in all_keys:
                if key_info.get("Name") == key_name:
                    logger.debug(f"IPNS key '{key_name}' found.")
                    return True
            logger.debug(f"IPNS key '{key_name}' not found in list.")
            return False
        except SciPFSException as e:
            # Log the error but don't let it propagate as a fatal error for a check method.
            # Treat as "key not found" or "cannot determine existence."
            logger.warning(f"Could not determine if IPNS key '{key_name}' exists due to an error: {e}")
            return False # Or re-raise if strict error handling is preferred

    def publish_to_ipns(self, key_name: str, cid: str, lifetime: str = "24h") -> Dict:
        """Publish a CID to an IPNS name using the Go wrapper.
        Returns a dictionary with publish details (e.g., {"Name": "ipns_name", "Value": "/ipfs/cid"}).
        """
        if not self.is_go_wrapper_available():
            raise IPFSConnectionError(self.go_wrapper_error or "Go wrapper not available for publish_to_ipns.")

        # Ensure the CID is presented as an IPFS path for the Go helper's -path argument
        ipfs_path = cid if cid.startswith('/ipfs/') else f"/ipfs/{cid}"

        try:
            # Go helper 'publish' command expects: -key-name <name> -path <ipfs_path> -lifetime <duration>
            publish_data = self._execute_go_wrapper_command_json(
                "publish_ipns",
                "-key-name", key_name,
                "-path", ipfs_path, # Changed from --cid to -path and ensured /ipfs/ prefix
                "-lifetime", lifetime,
                timeout_seconds=120 # Publishing can take time
            )
            if publish_data and "Name" in publish_data and "Value" in publish_data:
                logger.info(f"Successfully published path {ipfs_path} to IPNS key '{key_name}' (IPNS Name: {publish_data['Name']}) via Go wrapper.")
                return publish_data
            else:
                logger.error(f"IPNS publish for key '{key_name}', path '{ipfs_path}' via Go wrapper returned unexpected data: {publish_data}")
                raise RuntimeError(f"IPNS publish for '{key_name}' returned unexpected data.")
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper failed to publish to IPNS for key '{key_name}', path '{ipfs_path}': {e}")
            # Check for specific error message from Go wrapper if key does not exist
            if "no key by the given name was found" in str(e).lower() or "key does not exist" in str(e).lower():
                 raise SciPFSGoWrapperError(f"Cannot publish to IPNS: Key '{key_name}' does not exist. Original error: {e}") from e
            raise RuntimeError(f"Go wrapper failed to publish to IPNS for key '{key_name}', path '{ipfs_path}': {e}") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred during IPNS publish for key '{key_name}', path '{ipfs_path}': {e}", exc_info=True)
            if isinstance(e, SciPFSException): # Re-raise if it's already one of our specific exceptions
                raise
            raise RuntimeError(f"Unexpected error publishing to IPNS for key '{key_name}', path '{ipfs_path}': {str(e)}") from e

    def resolve_ipns_name(self, ipns_name: str) -> str:
        """Resolve an IPNS name to an IPFS path using the Go wrapper.
        Timeout for IPNS resolution can be long.
        """
        if not self.is_go_wrapper_available():
            raise IPFSConnectionError(self.go_wrapper_error or "Go wrapper not available for resolve_ipns_name.")

        try:
            logger.debug(f"Resolving IPNS name '{ipns_name}' via Go wrapper...")
            # Go helper 'resolve_ipns' command: `scipfs_go_helper -api <addr> resolve_ipns --ipns-name <name>`
            # Expected JSON: {"success": true, "data": {"Path": "/ipfs/cid"}}
            # The Go wrapper uses `ipfs name resolve` which is suitable.
            # The python-ipfs-http-client equivalent was client.name.resolve(), which also calls /api/v0/name/resolve
            
            # Based on scipfs_go_wrapper.go, the command is "resolve_ipns" and arguments are "--ipns-name"
            # Let's ensure we use the correct command name as per the Go wrapper's main() switch statement.
            # Looking at scipfs_go_wrapper.go, the command is indeed `resolve_ipns`
            # and it takes `--ipns-name`
            
            # Previous implementation might have used a different command name like "resolve".
            # Sticking to "resolve_ipns" as per the latest Go wrapper structure.
            response_data = self._execute_go_wrapper_command_json(
                "resolve_ipns", 
                "--ipns-name", ipns_name, 
                # "--nocache", "true", # Optional: add if necessary, default in Go wrapper is true
                # "--recursive", "true", # Optional: add if necessary, default in Go wrapper is true
                timeout_seconds=120 # Resolution can take time
            )
            
            resolved_path = response_data.get("Path") # Go wrapper returns {"Path": "value"}
            if resolved_path and (resolved_path.startswith("/ipfs/") or resolved_path.startswith("/ipns/")):
                logger.info(f"Successfully resolved IPNS name '{ipns_name}' to '{resolved_path}' via Go wrapper.")
                return resolved_path
            else:
                logger.error(f"IPNS resolve for '{ipns_name}' via Go wrapper returned unexpected data or no path: {response_data}")
                raise SciPFSFileNotFoundError(f"Could not resolve IPNS name '{ipns_name}'. Path: {resolved_path}")
        except SciPFSGoWrapperError as e:
            if "could not resolve name" in str(e).lower() or "no record" in str(e).lower() or "routing:not found" in str(e).lower() or "failed to find any peer in table" in str(e).lower():
                logger.warning(f"Failed to resolve IPNS name '{ipns_name}': {e}")
                raise SciPFSFileNotFoundError(f"Could not resolve IPNS name '{ipns_name}': {e}") from e
            logger.error(f"Go wrapper failed to resolve IPNS name '{ipns_name}': {e}")
            raise RuntimeError(f"Go wrapper failed to resolve IPNS name '{ipns_name}': {e}") from e
        except TimeoutError as e:
            logger.error(f"Timeout resolving IPNS name '{ipns_name}': {e}")
            raise SciPFSFileNotFoundError(f"Timeout resolving IPNS name '{ipns_name}': {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error resolving IPNS name '{ipns_name}': {e}", exc_info=True)
            if isinstance(e, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error during resolve_ipns_name via Go wrapper: {str(e)}")

    def list_pinned_cids(self, timeout: int = 10) -> Dict[str, Dict[str, str]]:
        """Get a dictionary of all pinned CIDs mapping to their pin type information.
        
        Args:
            timeout: Timeout in seconds for the operation.
            
        Returns:
            A dictionary where keys are CID strings and values are dictionaries 
            e.g., {"cid1": {"Type": "recursive"}, "cid2": {"Type": "direct"}}.
        """
        try:
            # The Go wrapper subcommand is 'list_pinned_cids'
            # It now returns a map like {"cid1": "recursive", "cid2": "direct", ...}
            # The python client needs to transform this to {"cid1": {"Type": "recursive"}, ...}
            raw_pinned_map = self._execute_go_wrapper_command_json(
                "list_pinned_cids", 
                "--pin-type", "all", 
                timeout_seconds=timeout
            )
            
            # raw_pinned_map is expected to be Dict[str, str] from the Go helper
            if isinstance(raw_pinned_map, dict):
                transformed_map = { 
                    cid_str: {"Type": type_str} 
                    for cid_str, type_str in raw_pinned_map.items()
                }
                logger.debug(f"Retrieved and transformed {len(transformed_map)} pinned CIDs with types.")
                return transformed_map
            else:
                logger.error(f"Failed to parse pinned CIDs and types from response, expected dict, got: {type(raw_pinned_map)}, data: {raw_pinned_map}")
                return {} # Return empty dict on parsing failure

        except SciPFSGoWrapperError as e:
            logger.error(f"Error getting pinned CIDs via Go wrapper: {e}")
            return {} 
        except TimeoutError as e: # Specifically catch TimeoutError from _execute_go_wrapper_command_json
            logger.error(f"Timeout getting pinned CIDs: {e}")
            raise # Re-raise TimeoutError to be caught by cli.py
        except Exception as e: # Catch any other unexpected exceptions
            logger.error(f"Unexpected error getting pinned CIDs: {e}", exc_info=True)
            return {} # Return empty dict for safety on other errors

    def find_providers(self, cid: str, timeout: int = 60) -> Set[str]:
        """Find providers for a given CID using the Go wrapper.
        Returns a set of Peer ID strings.
        Timeout is for the underlying 'ipfs dht findprovs' command.
        """
        if not self.is_go_wrapper_available():
            raise IPFSConnectionError(self.go_wrapper_error or "Go wrapper not available for find_providers.")

        try:
            # Go helper 'dht_find_providers' command (renamed in Go wrapper)
            # Arguments: --cid <cid>, --num-providers <val> (Go wrapper has num-providers, Python API has timeout for command execution itself)
            # The Go wrapper's dht_find_providers has --num-providers, not --timeout.
            # The Python method's `timeout` param is for the subprocess execution of the Go helper.
            # Let's keep Python's `timeout` as the overall timeout for the subprocess call.
            # The Go wrapper `dht_find_providers` uses `ipfs routing findprovs --num-providers=<val> <cid>`
            # The internal timeout for `ipfs routing findprovs` is managed by IPFS daemon.
            # We need to pass the --num-providers argument, which is not currently done.
            # Let's add a default or make it configurable. For now, let's use the Go wrapper's default of 20.
            # The Go wrapper subcommand 'dht_find_providers' takes '--cid' and '--num-providers'.
            
            # The original ipfshttpclient had client.dht.find_providers(cid, num_providers=20, timeout=timeout)
            # The Go wrapper has num_providers parameter with default 20.
            # Let's adjust the python client to pass num_providers if we want to override the go default.
            # For now, let's call it as is, relying on Go wrapper default for num_providers.
            # Or, pass the arguments as they are defined in the Go wrapper flag parsing.

            response_data = self._execute_go_wrapper_command_json(
                "dht_find_providers", # This now matches the renamed Go subcommand
                "--cid", cid,
                # Assuming the Go wrapper's default for num-providers (20) is acceptable
                # If we want to control num-providers from Python, we'd add it here:
                # "--num-providers", str(some_num_providers_value), 
                timeout_seconds=timeout + 10 # Overall timeout slightly longer
            )
            
            providers_list = response_data.get("providers")
            if isinstance(providers_list, list):
                logger.info(f"Found {len(providers_list)} providers for CID {cid} via Go wrapper.")
                return set(str(p) for p in providers_list) # Ensure all are strings
            else:
                logger.error(f"Providers list for CID {cid} via Go wrapper returned unexpected data format: {providers_list}")
                # If providers_list is None (key missing) and response was success, it means no providers were found.
                if providers_list is None and response_data.get("success", False):
                    logger.info(f"No providers found for CID {cid} (empty list from Go wrapper).")
                    return set() # Return empty set for no providers found
                raise RuntimeError(f"Providers list for CID {cid} returned unexpected data format from Go wrapper.")
        except SciPFSGoWrapperError as e:
            # Specific error for findprovs if it returns an error message like "context deadline exceeded" from the IPFS command itself
            if "context deadline exceeded" in str(e).lower() and "dht_find_providers" in str(e).lower():
                 logger.warning(f"Timeout finding providers for CID {cid} (IPFS command timeout {timeout}s): {e}")
                 # Convert to subprocess.TimeoutExpired for consistency if cli.py handles that for this command
                 # For now, return empty set as it means no providers found within timeout
                 raise TimeoutError(f"Timeout ({timeout}s) finding providers for CID {cid}.") from e
            logger.error(f"Go wrapper failed to find providers for CID {cid}: {e}")
            raise RuntimeError(f"Go wrapper failed to find providers for CID {cid}: {e}") from e
        except TimeoutError as e: # This catches overall timeout from _execute_go_wrapper_command_json
            logger.error(f"Overall timeout finding providers for CID {cid} via Go wrapper: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error finding providers for CID {cid}: {e}", exc_info=True)
            if isinstance(e, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error finding providers for CID {cid}: {e}")

    def get_daemon_info(self) -> Optional[Dict]:
        """Get daemon information (ID, version, addresses) using the Go wrapper.
        Returns a dictionary of daemon info, or None on failure to parse/execute.
        Specific errors are raised by _execute_go_wrapper_command_json.
        """
        if not self.is_go_wrapper_available():
            # This method might be called by check_ipfs_daemon before it raises an error for wrapper not found.
            # So, if wrapper path is None here, we should indicate that.
            self.go_wrapper_error = self.go_wrapper_error or f"Go wrapper ('{self.go_wrapper_executable_name}') not found."
            logger.error(f"Cannot get daemon info: {self.go_wrapper_error}")
            raise IPFSConnectionError(self.go_wrapper_error) 

        try:
            # Go helper 'daemon_info' command: `scipfs_go_helper -api <addr> daemon_info`
            # Expected JSON: {"success": true, "data": {"ID": "peerid", "Version": "0.x.y", ...}}
            daemon_info_data = self._execute_go_wrapper_command_json("daemon_info", timeout_seconds=30)
            
            # _execute_go_wrapper_command_json returns the "data" field upon success.
            # So, daemon_info_data is already the dictionary we need (e.g., {"ID": ..., "Version": ...})
            if isinstance(daemon_info_data, dict) and "ID" in daemon_info_data: # Check for essential field
                logger.debug(f"Successfully retrieved daemon info via Go wrapper: {daemon_info_data}")
                return daemon_info_data
            else:
                logger.error(f"Daemon info from Go wrapper is not a valid dictionary or missing 'ID': {daemon_info_data}")
                # This case implies _execute_go_wrapper_command_json returned something unexpected despite success flag from go_helper
                raise SciPFSGoWrapperError(f"Daemon info from Go wrapper was malformed: {daemon_info_data}")
        except SciPFSGoWrapperError as e:
            # Log the error but let check_ipfs_daemon or other callers handle the exception propagation.
            # This method is a getter; the caller decides if error is fatal.
            logger.warning(f"SciPFSGoWrapperError getting daemon info: {e}")
            raise # Re-raise the specific wrapper error
        except TimeoutError as e:
            logger.warning(f"Timeout getting daemon info: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting daemon info: {e}", exc_info=True)
            # Wrap in SciPFSGoWrapperError if it's an unexpected failure during this specific operation.
            if not isinstance(e, SciPFSException):
                 raise SciPFSGoWrapperError(f"Unexpected error getting daemon info: {e}") from e
            raise # Re-raise if already a SciPFSException

    def get_local_peer_id(self) -> Optional[str]:
        """Get the local IPFS node's Peer ID using the Go wrapper.
        Returns the Peer ID string or None if not available.
        This is mostly a convenience wrapper around get_daemon_info.
        """
        # This method might be called during __init__ via check_ipfs_daemon.
        # Ensure is_go_wrapper_available is checked or rely on get_daemon_info to do so.
        if not self.is_go_wrapper_available():
            logger.warning("Cannot get local peer ID: Go wrapper not available.")
            return None # Or raise IPFSConnectionError, but None is fine for a simple getter if init handles overall failure.

        try:
            daemon_info = self.get_daemon_info()
            if daemon_info and "ID" in daemon_info:
                peer_id = daemon_info["ID"]
                # Cache it in client_id_dict for consistency, though get_daemon_info already might have.
                self.client_id_dict = daemon_info 
                return peer_id
            else:
                logger.warning(f"Could not extract Peer ID from daemon_info: {daemon_info}")
                return None
        except SciPFSException as e: # Catch SciPFSGoWrapperError, TimeoutError, IPFSConnectionError from get_daemon_info
            logger.warning(f"Failed to get daemon info for Peer ID retrieval: {e}")
            # Store the error message if it came from get_daemon_info setting self.go_wrapper_error
            if isinstance(e, SciPFSGoWrapperError) and not self.go_wrapper_error:
                 self.go_wrapper_error = str(e)
            return None

    def _execute_go_wrapper_command_json(self, go_command: str, *args: str, input_data: Optional[str] = None, timeout_seconds: int = 120) -> Dict:
        """Execute a command using the Go wrapper and expect a JSON response.
        Parses the JSON and returns the content of the 'data' field if 'success' is true.
        Raises SciPFSGoWrapperError on failure (non-zero exit, JSON error, or 'success': false).
        Raises TimeoutError if the subprocess times out.
        """
        if not self.go_wrapper_path: # Should be caught by is_go_wrapper_available in public methods
            raise SciPFSGoWrapperError("Go wrapper executable path not set.")

        command_list = [self.go_wrapper_path, "-api", self.api_addr, go_command] + list(args)
        
        process_input = None
        if input_data is not None:
            process_input = input_data
            # For safety, if passing input data, log only type or presence, not content unless sure it's safe
            logger.debug(f"Executing Go wrapper command: {' '.join(command_list)} with input_data (type: {type(input_data)})")
        else:
            logger.debug(f"Executing Go wrapper command: {' '.join(command_list)}")

        try:
            result = subprocess.run(
                command_list, 
                capture_output=True, 
                text=True, 
                check=False, # We check returncode manually 
                timeout=timeout_seconds,
                input=process_input
            )

            stdout_val = result.stdout.strip() if result.stdout else ""
            stderr_val = result.stderr.strip() if result.stderr else ""

            if result.returncode == 0:
                try:
                    response_json = json.loads(stdout_val)
                    if response_json.get("success") is True:
                        logger.debug(f"Go command '{go_command}' successful. Response data: {response_json.get('data')}")
                        return response_json.get("data", {}) # Return data field or empty dict if data is missing but success
                    else:
                        error_msg = response_json.get("error", "Unknown error from Go wrapper (success was false).")
                        detailed_error = f"Go command '{go_command}' reported failure: {error_msg}. stdout: {stdout_val}"
                        logger.error(detailed_error)
                        raise SciPFSGoWrapperError(detailed_error)
                except json.JSONDecodeError as e_json:
                    # Successful exit code but stdout was not valid JSON.
                    detailed_error = f"Failed to decode JSON response from successful Go command '{go_command}'. stdout: {stdout_val}. Error: {e_json}"
                    logger.error(detailed_error)
                    raise SciPFSGoWrapperError(detailed_error) from e_json
            else: # Non-zero return code indicates an error from the Go helper itself.
                  # stderr should contain the JSON error message from Go helper's common error response.
                try:
                    error_json = json.loads(stderr_val)
                    error_msg_from_go = error_json.get("error", stderr_val) # Use raw stderr if 'error' field missing
                except json.JSONDecodeError:
                    error_msg_from_go = stderr_val if stderr_val else "No stderr output from Go wrapper."
                
                # Include stdout as well if it has content, might be useful for debugging go_helper issues
                full_error_details = f"Go command '{go_command}' failed with exit code {result.returncode}. Error: {error_msg_from_go}"
                if stdout_val:
                    full_error_details += f" stdout: {stdout_val}"

                logger.error(full_error_details)
                raise SciPFSGoWrapperError(full_error_details)

        except FileNotFoundError: # Should not happen if self.go_wrapper_path is valid
            logger.error(f"Go wrapper executable '{self.go_wrapper_path}' not found during command execution for '{go_command}'.")
            raise IPFSConnectionError(f"Go wrapper executable '{self.go_wrapper_path}' not found.") from None
        except subprocess.TimeoutExpired as e_timeout:
            logger.error(f"Timeout ({timeout_seconds}s) executing Go command '{go_command}'.")
            raise TimeoutError(f"Timeout executing Go command '{go_command}'.") from e_timeout
        except Exception as e_unexpected:
            logger.error(f"An unexpected error occurred in _execute_go_wrapper_command_json for '{go_command}': {e_unexpected}", exc_info=True)
            raise SciPFSGoWrapperError(f"Unexpected error executing Go command '{go_command}': {e_unexpected}") from e_unexpected

    def _check_go_wrapper(self) -> bool:
        # This method is effectively replaced by is_go_wrapper_available() and the logic in _find_go_wrapper().
        # Keeping it for now to satisfy the outline, but it should be removed or marked deprecated.
        logger.warning("_check_go_wrapper() is deprecated; use is_go_wrapper_available().")
        return self.is_go_wrapper_available()

# Example usage (for testing module directly)
if __name__ == '__main__':
    # Setup basic logging for direct script testing
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Testing IPFSClient directly...")
    
    # Specify a required version for testing the check
    # Ensure your Kubo daemon meets this or is lower to test different paths.
    # For example, if your Kubo is 0.23.0, set this to (0,23,0) for success, or (0,24,0) for failure.
    test_required_version = (0, 22, 0) 
    
    test_api_addr = "/ip4/127.0.0.1/tcp/5001" # Default, ensure your IPFS daemon is at this address

    try:
        client = IPFSClient(api_addr=test_api_addr, required_version_tuple=test_required_version)
        
        # This check_ipfs_daemon() is now crucial and would be called by CLI.
        client.check_ipfs_daemon()
        logger.info(f"IPFSClient initialized. Go wrapper: {client.go_wrapper_path} (v{client.go_wrapper_version})")
        logger.info(f"Daemon version: {client.get_version_str()}")

        # Test add_json and get_json
        logger.info("\n--- Testing add_json and get_json ---")
        json_data = {"hello": "world", "scipfs_test": 123}
        try:
            cid_json = client.add_json(json_data)
            logger.info(f"add_json successful. CID: {cid_json}")
            retrieved_json = client.get_json(cid_json)
            logger.info(f"get_json successful. Retrieved: {retrieved_json}")
            assert retrieved_json == json_data, "Retrieved JSON does not match original!"
            logger.info("JSON add/get assertion passed.")
        except SciPFSException as e:
            logger.error(f"Error during JSON add/get test: {e}")

        # Test add_file and get_file
        logger.info("\n--- Testing add_file and get_file ---")
        dummy_file = Path("ipfs_client_test_dummy.txt")
        dummy_file.write_text("This is a test file for IPFSClient.")
        dummy_output_path = Path("ipfs_client_test_dummy_downloaded.txt")
        try:
            cid_file = client.add_file(dummy_file, pin=True)
            logger.info(f"add_file successful. CID: {cid_file}")
            client.get_file(cid_file, dummy_output_path)
            logger.info(f"get_file successful. Downloaded to: {dummy_output_path}")
            assert dummy_output_path.read_text() == dummy_file.read_text(), "Downloaded file content mismatch!"
            logger.info("File add/get assertion passed.")
            # Test unpin
            logger.info(f"Attempting to unpin CID: {cid_file}")
            client.unpin(cid_file)
            logger.info(f"Unpin call for {cid_file} completed (check node for actual status).")

        except SciPFSException as e:
            logger.error(f"Error during file add/get test: {e}")
        finally:
            if dummy_file.exists(): dummy_file.unlink()
            if dummy_output_path.exists(): dummy_output_path.unlink()

        # Test IPNS key generation and listing (use a unique name)
        logger.info("\n--- Testing IPNS key operations ---")
        test_key_name = f"scipfs-test-key-{Path(dummy_file.name).stem}" # Unique enough for tests
        try:
            logger.info(f"Generating IPNS key: {test_key_name}")
            key_info_gen = client.generate_ipns_key(test_key_name)
            logger.info(f"generate_ipns_key successful: {key_info_gen}")
            assert key_info_gen["Name"] == test_key_name

            logger.info("Listing IPNS keys...")
            keys = client.list_ipns_keys()
            logger.info(f"list_ipns_keys successful. Found {len(keys)} keys.")
            assert any(k["Name"] == test_key_name for k in keys), "Generated key not found in list!"
            logger.info("IPNS key gen/list assertion passed.")

            # Test publish and resolve (using a known CID, e.g., the JSON one)
            if 'cid_json' in locals() and cid_json: # Check if cid_json was successfully created
                logger.info(f"\n--- Testing IPNS publish and resolve for key {test_key_name} with CID {cid_json} ---")
                pub_info = client.publish_to_ipns(test_key_name, cid_json, lifetime="1m") # Short lifetime for test
                logger.info(f"publish_to_ipns successful: {pub_info}")
                ipns_path_to_resolve = pub_info.get("Name") # This is /ipns/<peerID_of_key>
                if ipns_path_to_resolve:
                    logger.info(f"Attempting to resolve IPNS path: {ipns_path_to_resolve} (this may take a moment for propagation)")
                    # Add a small delay for IPNS propagation if needed, though local resolve might be fast
                    # import time; time.sleep(10) # Potentially needed for wider network tests
                    resolved_ipfs_path = client.resolve_ipns_name(ipns_path_to_resolve)
                    logger.info(f"resolve_ipns_name successful. Resolved to: {resolved_ipfs_path}")
                    expected_path = f"/ipfs/{cid_json}"
                    assert resolved_ipfs_path == expected_path, f"Resolved path mismatch! Expected {expected_path}, Got {resolved_ipfs_path}"
                    logger.info("IPNS publish/resolve assertion passed.")
                else:
                    logger.warning("Skipping IPNS resolve test as IPNS path was not returned from publish.")    
            else:
                logger.warning("Skipping IPNS publish/resolve test as prerequisite JSON CID not available.")

            # Clean up the test key
            # Note: remove_ipns_key method is not in the provided outline but would be good for cleanup
            # For now, manual removal might be needed: `ipfs key rm scipfs-test-key...`
            logger.info(f"Test key '{test_key_name}' may need to be manually removed from your IPFS node.")

        except SciPFSException as e:
            logger.error(f"Error during IPNS key operations test: {e}")
        except AssertionError as e_assert:
            logger.error(f"Assertion failed during IPNS tests: {e_assert}")

        # Test listing pinned CIDs
        logger.info("\n--- Testing list_pinned_cids ---")
        try:
            pinned_set = client.list_pinned_cids(timeout=15)
            logger.info(f"list_pinned_cids successful. Found {len(pinned_set)} pinned items.")
            # Example: Check if previously added file CID is in the pinned list (if it was pinned and not unpinned)
            if 'cid_file' in locals() and cid_file in pinned_set:
                logger.info(f"Test file CID {cid_file} is in the pinned list.")
            for p_cid in list(pinned_set)[:5]: # Print first 5 pins
                logger.debug(f"  Pinned: {p_cid}")
        except SciPFSException as e:
            logger.error(f"Error during list_pinned_cids test: {e}")

        # Test find_providers (using a known CID)
        if 'cid_json' in locals() and cid_json:
            logger.info(f"\n--- Testing find_providers for CID {cid_json} ---")
            try:
                providers = client.find_providers(cid_json, timeout=30)
                logger.info(f"find_providers for {cid_json} found {len(providers)} providers.")
                for provider_peer_id in list(providers)[:3]: # Print first 3 found providers
                    logger.debug(f"  Provider: {provider_peer_id}")
            except SciPFSException as e:
                logger.error(f"Error during find_providers test for {cid_json}: {e}")
        else:
            logger.warning("Skipping find_providers test as JSON CID not available.")

    except IPFSConnectionError as e:
        logger.error(f"IPFS Connection Error during test: {e}")
        logger.error("Please ensure your IPFS daemon is running and accessible, and scipfs_go_helper is built and in PATH.")
    except KuboVersionError as e:
        logger.error(f"IPFS Version Error during test: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during IPFSClient direct testing: {e}", exc_info=True)

    logger.info("\nIPFSClient direct testing finished.")
