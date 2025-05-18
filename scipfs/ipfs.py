import logging
from pathlib import Path
from typing import Dict, Optional, List, Set
import json
import subprocess # Import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom Exceptions
class SciPFSException(Exception):
    """Base exception for scipfs client errors."""
    pass

class ConnectionError(SciPFSException):
    """Raised for errors connecting to IPFS or the Go wrapper."""
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

class FileNotFoundError(SciPFSException, FileNotFoundError):
    """Raised when a local file to be added is not found."""
    # Inherits from built-in FileNotFoundError for compatibility if needed
    # but also from SciPFSException for a common base.
    pass


class IPFSClient:
    """Manages interactions with an IPFS node using the scipfs_go_helper.
    All IPFS operations are now routed through a local Go executable.
    """
    
    def __init__(self, addr: str = "/ip4/127.0.0.1/tcp/5001"):
        """Initialize IPFS client, detect Go wrapper, and check its version."""
        self.api_addr = addr  # Store for the Go wrapper
        self.go_wrapper_executable_name = "scipfs_go_helper"
        self.go_wrapper_path: Optional[str] = None
        self.go_wrapper_version: Optional[str] = None
        self.go_wrapper_error: Optional[str] = None
        self.client_id_dict: Optional[Dict] = None # To store Peer ID info from Go Wrapper
        self.client: Optional[object] = None # ipfshttpclient.Client is no longer used.

        possible_paths = [
            f"./{self.go_wrapper_executable_name}",  # Check current directory
            self.go_wrapper_executable_name          # Check PATH
        ]

        for path_attempt in possible_paths:
            try:
                cmd = [path_attempt, "version"]
                logger.debug(f"Attempting to find Go wrapper at: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
                
                try:
                    response_json = json.loads(result.stdout)
                    if response_json.get("success") and "version" in response_json.get("data", {}):
                        self.go_wrapper_path = path_attempt
                        self.go_wrapper_version = response_json["data"]["version"]
                        logger.info(
                            f"Successfully found and verified SciPFS Go Helper version {self.go_wrapper_version} at '{self.go_wrapper_path}' using API '{self.api_addr}'."
                        )
                        break  # Found and verified
                    else:
                        logger.warning(
                            f"Go wrapper at '{path_attempt}' ran but gave unexpected version output: {result.stdout.strip()}"
                        )
                except json.JSONDecodeError:
                    logger.warning(
                        f"Go wrapper at '{path_attempt}' ran but gave non-JSON output for version: {result.stdout.strip()}"
                    )
            except FileNotFoundError:
                logger.debug(f"Go wrapper not found at '{path_attempt}'.")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Go wrapper at '{path_attempt}' failed to run or returned error for version command. stderr: {e.stderr.strip()}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout checking Go wrapper at '{path_attempt}' with version command.")
            except Exception as e: 
                logger.error(f"Unexpected error checking Go wrapper at '{path_attempt}': {e}")

        if not self.go_wrapper_path:
            self.go_wrapper_error = f"SciPFS Go Helper ('{self.go_wrapper_executable_name}') not found or non-functional. Checked: {possible_paths}. Please ensure it is built and in your PATH or current directory."
            logger.error(self.go_wrapper_error)
            # Raise connection error if wrapper is essential and not found, to prevent further ops.
            raise ConnectionError(self.go_wrapper_error)
        
        # Attempt to get and cache local Peer ID using the Go wrapper during initialization.
        try:
            # get_local_peer_id uses _execute_go_wrapper_command_json which calls daemon_info
            peer_id = self.get_local_peer_id()
            if peer_id:
                logger.info(f"Successfully connected to IPFS node via Go wrapper. Peer ID: {peer_id}")
                # self.client_id_dict is populated by get_local_peer_id if successful
            else:
                # This might happen if daemon_info fails for reasons other than wrapper not found (e.g. daemon not running)
                # The ConnectionError for wrapper not found is raised above.
                # If get_local_peer_id returns None here, it means daemon_info failed.
                daemon_error_msg = self.go_wrapper_error or "Failed to retrieve Peer ID using Go wrapper (daemon_info failed)."
                logger.error(f"Could not retrieve Peer ID from IPFS node at {self.api_addr} using Go wrapper. Daemon might not be running or accessible. Error: {daemon_error_msg}")
                raise ConnectionError(f"Could not get Peer ID from IPFS node at {self.api_addr}. Error: {daemon_error_msg}")
        except SciPFSException as e:
             # Catch SciPFS specific exceptions from get_local_peer_id (like TimeoutError or SciPFSGoWrapperError from daemon_info)
            logger.error(f"Failed to get Peer ID during IPFSClient initialization via Go wrapper: {e}")
            raise ConnectionError(f"Failed to initialize IPFSClient due to error getting Peer ID: {e}") from e
        

    def is_go_wrapper_available(self) -> bool:
        """Check if the Go wrapper was successfully found and verified."""
        return self.go_wrapper_path is not None and self.go_wrapper_version is not None

    def add_file(self, file_path: Path) -> str:
        """Add a file to IPFS using the Go wrapper and return its CID."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for add_file."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot add file: {error_msg}")

        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        command = [
            self.go_wrapper_path,
            "-api", self.api_addr,
            "add_file",
            "--file", str(file_path) # Pass the file path as an argument to --file flag
        ]

        try:
            logger.debug(f"Executing Go wrapper command for add_file: {' '.join(command)}")
            # Timeout can be adjusted based on expected file sizes and network conditions.
            # Using a longer timeout than for 'pin' or 'daemon_info' as file adding can take time.
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=300) # 5 min timeout

            if result.returncode == 0:
                try:
                    response_json = json.loads(result.stdout)
                    if response_json.get("success") and response_json.get("data", {}).get("cid"):
                        cid = response_json["data"]["cid"]
                        logger.info(f"Successfully added file '{file_path}' via Go wrapper. CID: {cid}")
                        return cid
                    else:
                        error_msg = response_json.get("error", "Unknown error from Go wrapper's add_file")
                        logger.error(f"Go wrapper's add_file command failed for '{file_path}': {error_msg}. stdout: {result.stdout.strip()}")
                        raise RuntimeError(f"Go wrapper failed to add file '{file_path}': {error_msg}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON response from Go wrapper for add_file '{file_path}'. stdout: {result.stdout.strip()}")
                    raise RuntimeError(f"Failed to decode JSON from Go wrapper for add_file '{file_path}'")
            else:
                # Error output from Go wrapper is expected on stderr and should be JSON (or at least informative)
                error_detail = result.stderr.strip()
                try:
                    error_json = json.loads(error_detail)
                    error_detail = error_json.get("error", error_detail)
                except json.JSONDecodeError:
                    pass # Use raw stderr if not JSON
                
                logger.error(f"Go wrapper add_file command failed for '{file_path}' with exit code {result.returncode}. Stderr: {error_detail}")
                raise RuntimeError(f"Go wrapper command for add_file '{file_path}' failed with exit {result.returncode}: {error_detail}")

        except FileNotFoundError: # This will catch our custom one now
            logger.error(f"Go wrapper executable '{self.go_wrapper_path}' not found for add_file, though previously detected.")
            raise ConnectionError(f"Go wrapper executable '{self.go_wrapper_path}' suddenly not found.")
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout during 'add_file' command with Go wrapper for '{file_path}'.")
            raise TimeoutError(f"Timeout adding file '{file_path}' with Go wrapper.")
        except Exception as e:
            logger.error(f"An unexpected error occurred calling Go wrapper for add_file '{file_path}': {e}", exc_info=True)
            # For truly unexpected errors, re-raise or wrap in a generic SciPFSException or RuntimeError.
            # Let's use RuntimeError for now for consistency with other failure paths.
            if isinstance(e, SciPFSException):
                raise # Re-raise if it's already one of ours
            raise RuntimeError(f"Unexpected error adding file '{file_path}' with Go wrapper: {str(e)}")

    def get_file(self, cid: str, output_path: Path) -> None:
        """Download a file from IPFS by CID to the specified path using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for get_file."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot get file: {error_msg}")

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
            raise ConnectionError(f"Cannot pin: {error_msg}")

        command = [
            self.go_wrapper_path, # Use the discovered path
            "-api", self.api_addr, # Pass the API address
            "pin",
            cid
        ]
        try:
            # Increased timeout for potentially slow IPFS operations
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90) 
            
            if result.returncode == 0:
                try:
                    response_json = json.loads(result.stdout)
                    if response_json.get("success"):
                        logger.info("Successfully pinned CID %s via Go wrapper. Response: %s", cid, result.stdout.strip())
                        return # Success
                    else:
                        error_msg = response_json.get("error", "Unknown error from Go wrapper")
                        logger.error("Go wrapper failed to pin CID %s: %s", cid, error_msg)
                        raise RuntimeError(f"Go wrapper failed to pin CID {cid}: {error_msg}")
                except json.JSONDecodeError:
                    logger.error("Failed to decode JSON response from Go wrapper for pin CID %s. stdout: %s", cid, result.stdout)
                    raise RuntimeError(f"Failed to decode JSON from Go wrapper for pin CID {cid}")
            else:
                # Error output from Go wrapper is expected on stderr and should be JSON
                error_message = f"Go wrapper command failed with exit code {result.returncode}."
                try:
                    error_json = json.loads(result.stderr)
                    error_message += f" Error: {error_json.get('error', result.stderr.strip())}"
                except json.JSONDecodeError:
                    error_message += f" Stderr: {result.stderr.strip()}"
                
                logger.error(error_message + f" (CID: {cid})")
                raise RuntimeError(error_message)

        except FileNotFoundError:
            logger.error(f"Go wrapper executable '{self.go_wrapper_path}' not found for pin command, though it was previously detected.")
            raise ConnectionError(f"Go wrapper executable '{self.go_wrapper_path}' suddenly not found.")
        except subprocess.TimeoutExpired:
            logger.error("Timeout during 'pin' command with Go wrapper for CID %s", cid)
            raise TimeoutError(f"Timeout pinning CID {cid} with Go wrapper.")
        except Exception as e:
            logger.error("An unexpected error occurred calling Go wrapper for pin CID %s: %s", cid, e)
            if isinstance(e, SciPFSException):
                raise # Re-raise if it's already one of ours
            raise RuntimeError(f"Unexpected error pinning CID {cid} with Go wrapper: {e}")

    def get_json(self, cid: str) -> Dict:
        """Retrieve and parse JSON content from IPFS by CID using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for get_json."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot get JSON: {error_msg}")

        try:
            # _execute_go_wrapper_command_json should return the "data" part of the successful JSON response
            json_data = self._execute_go_wrapper_command_json("get_json_cid", "--cid", cid)
            if not isinstance(json_data, Dict):
                logger.error(f"Go wrapper returned non-dict data for get_json_cid (CID: {cid}). Type: {type(json_data)}. Data: {json_data}")
                raise RuntimeError(f"Go wrapper returned non-dictionary data for JSON content (CID: {cid})")
            logger.info(f"Successfully retrieved JSON for CID {cid} via Go wrapper.")
            return json_data
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper command 'get_json_cid' failed for CID {cid}: {e}")
            raise # The error from _execute_go_wrapper_command_json is already specific
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for get_json (CID {cid}): {e}")
            if isinstance(e, SciPFSException):
                raise # Re-raise if it's already one of ours
            raise RuntimeError(f"Unexpected error during get_json via Go wrapper for CID {cid}: {str(e)}")

    def add_json(self, data: Dict) -> str:
        """Add a JSON object to IPFS and return its CID using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for add_json."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot add JSON: {error_msg}")

        try:
            json_string = json.dumps(data)
        except TypeError as e:
            logger.error(f"Failed to serialize data to JSON for add_json: {e}. Data: {data}")
            raise ValueError(f"Invalid data provided for add_json, cannot serialize to JSON: {e}") from e

        try:
            response_data = self._execute_go_wrapper_command_json("add_json_data", input_data=json_string)
            
            if not isinstance(response_data, dict) or "cid" not in response_data:
                logger.error(f"Go wrapper returned unexpected data for add_json_data. Expected dict with 'cid'. Got: {response_data}")
                raise RuntimeError("Go wrapper returned invalid response for add_json_data")
            
            cid = response_data["cid"]
            logger.info(f"Successfully added JSON data via Go wrapper. CID: {cid}")
            return cid
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper command 'add_json_data' failed: {e}")
            raise # The error from _execute_go_wrapper_command_json is already specific
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for add_json: {e}")
            if isinstance(e, SciPFSException):
                raise # Re-raise if it's already one of ours
            raise RuntimeError(f"Unexpected error during add_json via Go wrapper: {str(e)}")

    def generate_ipns_key(self, key_name: str) -> Dict:
        """Generate a new IPNS key or return its information if it already exists, using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for generate_ipns_key."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot generate IPNS key: {error_msg}")

        try:
            # Current Python code uses type="rsa", size=2048 for ipfshttpclient.
            # The 'ipfs key gen' CLI command with '--type rsa' defaults to 2048 bits.
            key_info = self._execute_go_wrapper_command_json("gen_ipns_key", "--key-name", key_name, "--key-type", "rsa")
            
            if not isinstance(key_info, dict) or "Name" not in key_info or "Id" not in key_info:
                logger.error(f"Go wrapper returned unexpected data for gen_ipns_key. Expected dict with 'Name' and 'Id'. Got: {key_info}")
                raise RuntimeError(f"Go wrapper returned invalid response for gen_ipns_key ('{key_name}')")

            logger.info(f"Go wrapper successfully processed 'gen_ipns_key' for '{key_info['Name']}' with ID {key_info['Id']}")
            return key_info
        
        except SciPFSGoWrapperError as e:
            logger.warning(f"Go wrapper 'gen_ipns_key' for '{key_name}' failed (possibly already exists or other daemon error): {e}. Checking if key exists.")
            try:
                keys = self.list_ipns_keys()
                for key in keys:
                    if key['Name'] == key_name:
                        logger.info(f"Found existing IPNS key '{key['Name']}' with ID {key['Id']} after Go wrapper gen_ipns_key failed.")
                        return key
                logger.error(f"IPNS key '{key_name}' not found in list after Go wrapper gen_ipns_key failed. Original Go wrapper error: {e}")
                raise RuntimeError(f"Failed to generate IPNS key '{key_name}' via Go wrapper, and it does not appear to exist.") from e
            except SciPFSException as list_e:
                logger.error(f"Error while trying to list IPNS keys after failing to generate '{key_name}' via Go wrapper: {list_e}. Original Go error: {e}")
                raise RuntimeError(f"Failed to generate IPNS key '{key_name}' via Go wrapper and failed to verify existence due to: {list_e}") from list_e
            except Exception as list_e_unexpected:
                logger.error(f"Unexpected error listing IPNS keys after gen failure for '{key_name}': {list_e_unexpected}. Original Go error: {e}")
                raise RuntimeError(f"Unexpected error verifying key '{key_name}' after Go gen failure: {list_e_unexpected}") from list_e_unexpected
        
        except Exception as e_unhandled:
            logger.error(f"An unexpected error occurred during 'generate_ipns_key' for '{key_name}' using Go wrapper: {e_unhandled}")
            if isinstance(e_unhandled, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error in generate_ipns_key ('{key_name}'): {str(e_unhandled)}")

    def list_ipns_keys(self) -> List[Dict]:
        """List all IPNS keys using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for list_ipns_keys."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot list IPNS keys: {error_msg}")

        try:
            keys_data = self._execute_go_wrapper_command_json("list_ipns_keys_cmd")
            
            if not isinstance(keys_data, list):
                logger.error(f"Go wrapper returned non-list data for list_ipns_keys_cmd. Type: {type(keys_data)}. Data: {keys_data}")
                raise RuntimeError("Go wrapper returned invalid response for list_ipns_keys_cmd (expected a list)")
            
            # Validate structure of items in the list (optional, but good for robustness)
            validated_keys_list = []
            for item in keys_data:
                if isinstance(item, dict) and "Name" in item and "Id" in item:
                    validated_keys_list.append(item)
                else:
                    logger.warning(f"Go wrapper list_ipns_keys_cmd returned an invalid item in the list: {item}. Skipping.")
            
            logger.debug(f"Successfully listed {len(validated_keys_list)} IPNS keys via Go wrapper.")
            return validated_keys_list
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper command 'list_ipns_keys_cmd' failed: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for list_ipns_keys: {e}")
            if isinstance(e, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error during list_ipns_keys via Go wrapper: {str(e)}")

    def check_key_exists(self, key_name: str) -> bool:
        """Check if an IPNS key with the given name exists."""
        try:
            keys = self.list_ipns_keys()
            return any(key['Name'] == key_name for key in keys)
        except Exception:
            return False

    def publish_to_ipns(self, key_name: str, cid: str, lifetime: str = "24h") -> Dict:
        """Publish a CID to an IPNS name using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for publish_to_ipns."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot publish to IPNS: {error_msg}")

        path_to_publish = cid if cid.startswith(('/ipfs/', '/ipns/')) else f'/ipfs/{cid}'
        
        # The check_key_exists method now uses the (soon-to-be) Go-backed list_ipns_keys.
        if not self.check_key_exists(key_name):
            logger.warning(f"Attempting to publish with IPNS key '{key_name}' which does not appear to exist locally. This may fail or create the key implicitly if the IPFS daemon supports it.")
            # Unlike the old ipfshttpclient, `ipfs name publish` CLI (and thus the Go wrapper)
            # might create the key if it doesn't exist, but it will be a new random key,
            # not necessarily named `key_name` in the keystore unless `key_name` was `self`
            # or if a specific behavior of `ipfs name publish --key=<name_not_exist>` creates it with that name.
            # This warning is useful for consistency.

        try:
            args = [
                "--key-name", key_name,
                "--path", path_to_publish,
                "--lifetime", lifetime
            ]
            response_data = self._execute_go_wrapper_command_json("publish_ipns", *args)
            
            if not isinstance(response_data, dict) or "Name" not in response_data or "Value" not in response_data:
                logger.error(f"Go wrapper returned unexpected data for publish_ipns. Expected dict with 'Name' and 'Value'. Got: {response_data}")
                raise RuntimeError("Go wrapper returned invalid response for publish_ipns")

            logger.info(f"Successfully published {response_data['Value']} to IPNS name {response_data['Name']} (key: {key_name}) via Go wrapper.")
            return response_data
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper command 'publish_ipns' failed for key '{key_name}', path '{path_to_publish}': {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for publish_to_ipns (key '{key_name}', path '{path_to_publish}'): {e}")
            if isinstance(e, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error during publish_to_ipns via Go wrapper: {str(e)}")

    def resolve_ipns_name(self, ipns_name: str) -> str:
        """Resolve an IPNS name to its currently published IPFS path using the Go wrapper."""
        if not ipns_name.startswith("/ipns/"):
            # This check is maintained from original code for consistency of this Python method's input validation.
            # The underlying 'ipfs name resolve' CLI (and thus Go wrapper) can often handle bare k51... names.
            raise ValueError("IPNS name must start with /ipns/")

        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for resolve_ipns_name."
            logger.error(error_msg)
            raise ConnectionError(f"Cannot resolve IPNS name: {error_msg}")

        try:
            # Go wrapper defaults nocache=true, recursive=true, which matches desired behavior.
            args = ["--ipns-name", ipns_name]
            # Example if we wanted to control these from Python:
            # args.extend(["--nocache=true", "--recursive=true"]) 
            
            response_data = self._execute_go_wrapper_command_json("resolve_ipns", *args)
            
            if not isinstance(response_data, dict) or "Path" not in response_data:
                logger.error(f"Go wrapper returned unexpected data for resolve_ipns. Expected dict with 'Path'. Got: {response_data}")
                raise RuntimeError(f"Go wrapper returned invalid response for resolve_ipns ('{ipns_name}')")
            
            resolved_path = response_data["Path"]
            logger.info(f"Successfully resolved IPNS name {ipns_name} to {resolved_path} via Go wrapper.")
            return resolved_path
        
        except SciPFSGoWrapperError as e:
            # Specific handling for "could not resolve name" or similar, map to FileNotFoundError like original.
            # This requires inspecting the error message string from Go, which is fragile.
            # Ideally, Go wrapper would return specific error codes/types if possible.
            error_str = str(e).lower()
            if "could not resolve name" in error_str or "record not found" in error_str or "routing: not found" in error_str or "could not find record" in error_str:
                logger.warning(f"Could not resolve IPNS name {ipns_name} via Go wrapper: {e}")
                raise FileNotFoundError(f"Could not resolve IPNS name {ipns_name}. It may not exist or not be propagated yet.") from e
            
            logger.error(f"Go wrapper command 'resolve_ipns' failed for IPNS name '{ipns_name}': {e}")
            raise # Re-raise other SciPFSGoWrapperErrors
        
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for resolve_ipns_name ('{ipns_name}'): {e}")
            if isinstance(e, SciPFSException):
                raise
            raise RuntimeError(f"Unexpected error during resolve_ipns_name via Go wrapper: {str(e)}")

    def get_pinned_cids(self) -> set[str]:
        """Retrieve a set of all CIDs currently pinned by the local IPFS node using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for get_pinned_cids."
            logger.error(error_msg)
            # Consistent with original behavior, return empty set on major failure to connect/find wrapper.
            return set()

        try:
            # Current Python code specifically gets 'recursive' pins.
            response_data = self._execute_go_wrapper_command_json("list_pinned_cids", "--pin-type", "recursive")
            
            if not isinstance(response_data, dict) or "cids" not in response_data or not isinstance(response_data["cids"], list):
                logger.error(f"Go wrapper returned unexpected data for list_pinned_cids. Expected dict with a list 'cids'. Got: {response_data}")
                return set() # Return empty set on unexpected data structure
            
            cids_list = response_data["cids"]
            # Ensure all items in list are strings, as CIDs should be.
            valid_cids = {str(item) for item in cids_list if isinstance(item, str)}
            
            logger.info(f"Successfully retrieved {len(valid_cids)} pinned CIDs (recursive) via Go wrapper.")
            return valid_cids
        
        except SciPFSGoWrapperError as e:
            # This indicates the Go command itself failed (e.g. ipfs pin ls errored)
            logger.error(f"Go wrapper command 'list_pinned_cids' failed: {e}")
            return set() # Original code returns empty set on IPFS ErrorResponse
        
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for get_pinned_cids: {e}", exc_info=True)
            return set() # Return empty set on any other exception, consistent with original

    def find_providers(self, cid: str, timeout: int = 60) -> Set[str]:
        """Find peers providing a given CID using the Go wrapper.
        The timeout parameter applies to the execution of the Go wrapper process.
        """
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for find_providers."
            logger.error(error_msg)
            return set() # Consistent with original behavior on failure

        try:
            # The Go helper has a default for --num-providers=20, matching original code.
            # The timeout for _execute_go_wrapper_command_json_with_timeout needs to be implemented
            # or the existing _execute_go_wrapper_command_json needs to accept a timeout.
            # For now, let's assume _execute_go_wrapper_command_json can take a timeout or we make a variant.

            # Modifying _execute_go_wrapper_command_json to accept a timeout parameter.
            # This is a conceptual change to the helper; the edit below will reflect this.
            response_data = self._execute_go_wrapper_command_json(
                "find_providers_cid", 
                "--cid", cid, 
                # "--num-providers", "20", # Go helper defaults to 20
                timeout_seconds=timeout # Pass timeout to the helper execution
            )
            
            if not isinstance(response_data, dict) or \
               "providers" not in response_data or \
               not isinstance(response_data["providers"], list):
                logger.error(f"Go wrapper returned unexpected data for find_providers_cid. Expected dict with list 'providers'. Got: {response_data}")
                return set() 
            
            providers_list = response_data["providers"]
            valid_providers = {str(item) for item in providers_list if isinstance(item, str) and item.strip()}
            
            logger.info(f"Found {len(valid_providers)} providers for CID {cid} via Go wrapper.")
            return valid_providers
        
        except TimeoutError: # This would be raised by _execute_go_wrapper_command_json if it supports timeout
            logger.warning(f"Timeout occurred after {timeout} seconds during find_providers for CID {cid} via Go wrapper.")
            return set()
        except SciPFSGoWrapperError as e:
            logger.error(f"Go wrapper command 'find_providers_cid' failed for CID {cid}: {e}")
            return set() 
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling Go wrapper for find_providers (CID {cid}): {e}", exc_info=True)
            return set()

    def get_daemon_info(self) -> Optional[Dict]:
        """Get IPFS daemon info (Version, ID) using the Go wrapper."""
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or "Go wrapper not available for get_daemon_info."
            logger.error(error_msg)
            # Optionally, raise an error or return None to indicate failure
            # For doctor, it might be better to return None and let doctor report it.
            return None 

        # Assuming the Go wrapper has a 'daemon_info' subcommand
        # that returns JSON like: {"success": true, "data": {"id": "...", "version": "..."}}
        command = [self.go_wrapper_path, "-api", self.api_addr, "daemon_info"]
        try:
            logger.debug(f"Executing Go wrapper command: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)

            if result.returncode == 0:
                try:
                    response_json = json.loads(result.stdout)
                    if response_json.get("success") and "data" in response_json:
                        logger.info(f"Successfully fetched daemon_info via Go wrapper: {response_json['data']}")
                        return response_json["data"]
                    else:
                        error_msg = response_json.get("error", "Unknown error from Go wrapper's daemon_info")
                        logger.error(f"Go wrapper's daemon_info command failed: {error_msg}. stdout: {result.stdout.strip()}")
                        self.go_wrapper_error = f"daemon_info failed: {error_msg}"
                        return None
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON response from Go wrapper for daemon_info. stdout: {result.stdout.strip()}")
                    self.go_wrapper_error = "daemon_info bad JSON"
                    return None
            else:
                error_detail = result.stderr.strip()
                try:
                    # Attempt to parse stderr as JSON, as Go wrapper might output structured errors
                    error_json = json.loads(error_detail)
                    error_detail = error_json.get("error", error_detail)
                except json.JSONDecodeError:
                    pass # Use raw stderr if not JSON
                
                logger.error(f"Go wrapper daemon_info command failed with exit code {result.returncode}. Stderr: {error_detail}")
                self.go_wrapper_error = f"daemon_info exit code {result.returncode}: {error_detail}"
                return None

        except subprocess.TimeoutExpired:
            logger.error("Timeout during 'daemon_info' command with Go wrapper.")
            self.go_wrapper_error = "daemon_info timeout"
            return None
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"An unexpected error occurred calling Go wrapper for daemon_info: {e}", exc_info=True)
            self.go_wrapper_error = f"daemon_info unexpected error: {str(e)}"
            return None

    def get_local_peer_id(self) -> Optional[str]:
        """Returns the Peer ID of the connected IPFS node, obtained via the Go wrapper."""
        if self.client_id_dict and 'ID' in self.client_id_dict:
            return self.client_id_dict.get('ID')
        
        # If client_id_dict wasn't populated during __init__ or got cleared, try to fetch it.
        # This path would typically indicate an issue during initialization.
        logger.info("Attempting to get Peer ID via Go wrapper (get_local_peer_id)...")
        try:
            # The 'daemon_info' command in Go wrapper returns ID, AgentVersion etc.
            id_info = self._execute_go_wrapper_command_json("daemon_info") 
            peer_id = id_info.get("ID")
            if peer_id:
                logger.info(f"Successfully retrieved Peer ID via Go wrapper: {peer_id}")
                self.client_id_dict = id_info # Cache it
                return peer_id
            else:
                logger.warning("Go wrapper 'daemon_info' command did not return an 'ID' field in data.")
                return None
        except SciPFSException as e: # Catch SciPFSGoWrapperError, TimeoutError etc.
            logger.warning(f"Go wrapper 'daemon_info' command failed while attempting to get Peer ID: {e}")
            return None
        except Exception as e:
            logger.warning(f"An unexpected error occurred trying to get Peer ID via Go wrapper: {e}")
            return None
        
        # This line should ideally not be reached if Go wrapper is functional and daemon is responsive.
        logger.warning("Could not determine local Peer ID using the Go wrapper.")
        return None

    def _execute_go_wrapper_command_json(self, go_command: str, *args: str, input_data: Optional[str] = None, timeout_seconds: int = 120) -> Dict:
        """Execute a Go wrapper command that is expected to return JSON and parse it.
        Can optionally send input_data to the command's stdin and specify a timeout for the subprocess execution.
        """
        if not self.is_go_wrapper_available():
            error_msg = self.go_wrapper_error or f"Go wrapper not available for command '{go_command}'."
            logger.error(error_msg)
            raise SciPFSGoWrapperError(error_msg)

        command = [
            self.go_wrapper_path,
            "-api", self.api_addr,
            go_command,
            *args
        ]

        try:
            logger.debug(f"Executing Go wrapper command: {' '.join(command)} {'with input data' if input_data else ''} (timeout: {timeout_seconds}s)")
            process = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=False, 
                timeout=timeout_seconds, 
                input=input_data
            )

            if process.returncode == 0:
                try:
                    response_json = json.loads(process.stdout)
                    if response_json.get("success"):
                        # Assuming successful responses place their payload in "data"
                        # or the whole response is the data if "data" field is not present (e.g. for get_json_cid)
                        return response_json.get("data", response_json) 
                    else:
                        error_msg = response_json.get("error", f"Unknown error from Go wrapper's {go_command}")
                        logger.error(f"Go wrapper command '{go_command}' failed: {error_msg}. stdout: {process.stdout.strip()}")
                        raise SciPFSGoWrapperError(f"Go wrapper command '{go_command}' failed: {error_msg}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON response from Go wrapper for {go_command}. stdout: {process.stdout.strip()}")
                    raise SciPFSGoWrapperError(f"Failed to decode JSON from Go wrapper for {go_command}")
            else:
                error_detail = process.stderr.strip()
                try:
                    error_json = json.loads(error_detail)
                    error_detail = error_json.get("error", error_detail)
                except json.JSONDecodeError:
                    pass # Use raw stderr if not JSON
                logger.error(f"Go wrapper command '{go_command}' failed with exit code {process.returncode}. Stderr: {error_detail}")
                raise SciPFSGoWrapperError(f"Go wrapper command '{go_command}' failed with exit {process.returncode}: {error_detail}")
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout during '{go_command}' command with Go wrapper.")
            raise TimeoutError(f"Timeout during '{go_command}' with Go wrapper.")
        except SciPFSGoWrapperError:
            raise # Re-raise SciPFSGoWrapperError if already caught and processed
        except Exception as e:
            logger.error(f"An unexpected error occurred calling Go wrapper for {go_command}: {e}", exc_info=True)
            raise SciPFSGoWrapperError(f"Unexpected error during '{go_command}' with Go wrapper: {str(e)}") from e

    def _check_go_wrapper(self) -> bool:
        # This method is not provided in the original file or the code block
        # It's assumed to exist as it's called in get_local_peer_id
        # It's also not implemented in the original file or the code block
        # It's assumed to return a boolean indicating whether the Go wrapper is available
        # This is a placeholder and should be implemented based on the actual implementation
        return self.is_go_wrapper_available()
