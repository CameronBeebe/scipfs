import ipfshttpclient
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
    """Manages interactions with an IPFS node.
    
    Note: Currently using both ipfshttpclient and Go wrapper in parallel.
    Methods using ipfshttpclient:
    - get_file
    - get_json
    - add_json
    - generate_ipns_key
    - list_ipns_keys
    - check_key_exists
    - publish_to_ipns
    - resolve_ipns_name
    - get_pinned_cids
    - find_providers (with CLI fallback)
    
    Methods using Go wrapper:
    - add_file
    - pin
    - get_daemon_info
    
    Long-term plan: Migrate all methods to use the Go wrapper exclusively.
    """
    
    def __init__(self, addr: str = "/ip4/127.0.0.1/tcp/5001"):
        """Initialize IPFS client, detect Go wrapper, and check its version."""
        self.api_addr = addr  # Store for the Go wrapper
        self.go_wrapper_executable_name = "scipfs_go_helper"
        self.go_wrapper_path: Optional[str] = None
        self.go_wrapper_version: Optional[str] = None
        self.go_wrapper_error: Optional[str] = None
        self.client_id_dict: Optional[Dict] = None # Initialize attribute
        self.client: Optional[ipfshttpclient.Client] = None # Initialize client attribute

        possible_paths = [
            f"./{self.go_wrapper_executable_name}",  # Check current directory
            self.go_wrapper_executable_name          # Check PATH
        ]

        for path_attempt in possible_paths:
            try:
                # Use a lightweight command like "version" to check
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
                        # Continue to next path if this one gave bad output but didn't error

                except json.JSONDecodeError:
                    logger.warning(
                        f"Go wrapper at '{path_attempt}' ran but gave non-JSON output for version: {result.stdout.strip()}"
                    )
                    # Continue to next path

            except FileNotFoundError:
                logger.debug(f"Go wrapper not found at '{path_attempt}'.")
                # Will try next path or set error if this was the last one
            except subprocess.CalledProcessError as e:
                logger.warning(f"Go wrapper at '{path_attempt}' failed to run or returned error for version command. stderr: {e.stderr.strip()}")
                # Will try next path or set error
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout checking Go wrapper at '{path_attempt}' with version command.")
                # Will try next path or set error
            except Exception as e: # Catch any other unexpected errors during the check
                logger.error(f"Unexpected error checking Go wrapper at '{path_attempt}': {e}")


        if not self.go_wrapper_path:
            self.go_wrapper_error = f"SciPFS Go Helper ('{self.go_wrapper_executable_name}') not found or non-functional. Checked: {', '.join(possible_paths)}"
            logger.error(self.go_wrapper_error)
            # No need to raise ConnectionError here, let consuming code check go_wrapper_path/version
        
        # Initialize ipfshttpclient connection
        try:
            self.client = ipfshttpclient.connect(addr, timeout=90)
            self.client_id_dict = self.client.id() # Assign here after successful connect and id call
            logger.info("Successfully connected to IPFS node at %s. Peer ID: %s", addr, self.get_local_peer_id())
        except ipfshttpclient.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to IPFS node at {addr}. Is the IPFS daemon running? {e}")
            # self.client remains None
            raise ConnectionError(f"Could not connect to IPFS node at {addr}. Please ensure the IPFS daemon is running.") from e
        except Exception as e:
            logger.error("Failed to connect to IPFS node during general client init: %s", e)
            # self.client remains None
            raise ConnectionError(f"Could not connect to IPFS node at {addr} (unexpected error): {e}") from e

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
        """Download a file from IPFS by CID to the specified path."""
        try:
            content = self.client.cat(cid)
            output_path.write_bytes(content)
            logger.info("Downloaded CID %s to %s", cid, output_path)
        except Exception as e:
            logger.error("Failed to download CID %s: %s", cid, e)
            raise

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
        """Retrieve and parse JSON content from IPFS by CID."""
        try:
            content = self.client.cat(cid).decode("utf-8")
            return json.loads(content)
        except ipfshttpclient.exceptions.ErrorResponse as e:
            logger.error(f"Failed to retrieve JSON content for CID {cid} from IPFS: {e}")
            raise SciPFSException(f"IPFS error retrieving JSON for CID {cid}: {e}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON for CID {cid}. Content is not valid JSON: {e}")
            raise SciPFSException(f"Content for CID {cid} is not valid JSON.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred retrieving JSON for CID {cid}: {e}")
            raise SciPFSException(f"Unexpected error for CID {cid}: {e}") from e

    def add_json(self, data: Dict) -> str:
        """Add a JSON object to IPFS and return its CID."""
        try:
            cid = self.client.add_json(data)
            logger.info("Added JSON to IPFS with CID %s", cid)
            return cid
        except Exception as e:
            logger.error("Failed to add JSON to IPFS: %s", e)
            raise

    def generate_ipns_key(self, key_name: str) -> Dict:
        """Generate a new IPNS key or return its information if it already exists."""
        try:
            key_info = self.client.key.gen(key_name, type="rsa", size=2048)
            logger.info("Generated IPNS key '%s' with ID %s", key_info['Name'], key_info['Id'])
            return key_info
        except ipfshttpclient.exceptions.ErrorResponse as e:
            # Check if the error indicates the key already exists.
            # Older daemons might just raise a generic error that doesn't clearly state "already exists"
            # but the primary symptom is the failure of key.gen().
            # So, we'll try to list the keys and see if the desired key_name is present.
            logger.warning(f"Failed to generate IPNS key '{key_name}' directly (possibly already exists or other daemon error): {e}. Checking if key exists in list.")
            try:
                keys = self.list_ipns_keys()
                for key in keys:
                    if key['Name'] == key_name:
                        logger.info("Found existing IPNS key '%s' with ID %s after initial gen failed.", key['Name'], key['Id'])
                        return key
                # If not found in the list after the error, then it was a genuine error not related to existence.
                logger.error("IPNS key '%s' not found in list after initial gen failed. Original error: %s", key_name, e)
                raise RuntimeError(f"Failed to generate IPNS key '{key_name}', and it does not appear to exist.") from e
            except Exception as list_e: # Catch errors during the list_ipns_keys call
                logger.error("Error while trying to list IPNS keys after failing to generate '%s': %s. Original gen error: %s", key_name, list_e, e)
                raise RuntimeError(f"Failed to generate IPNS key '{key_name}' and failed to verify existence.") from list_e
        except Exception as e: # Catch other unexpected errors
            logger.error("An unexpected error occurred while generating IPNS key '%s': %s", key_name, e)
            raise RuntimeError(f"Unexpected error generating IPNS key '{key_name}'.") from e

    def list_ipns_keys(self) -> List[Dict]:
        """List all IPNS keys."""
        try:
            keys = self.client.key.list()['Keys']
            logger.debug("Found %d IPNS keys", len(keys))
            return keys
        except Exception as e:
            logger.error("Failed to list IPNS keys: %s", e)
            raise

    def check_key_exists(self, key_name: str) -> bool:
        """Check if an IPNS key with the given name exists."""
        try:
            keys = self.list_ipns_keys()
            return any(key['Name'] == key_name for key in keys)
        except Exception:
            return False

    def publish_to_ipns(self, key_name: str, cid: str, lifetime: str = "24h") -> Dict:
        """Publish a CID to an IPNS name."""
        if not cid.startswith("/ipfs/"):
            path_to_publish = f"/ipfs/{cid}"
        else:
            path_to_publish = cid
        
        try:
            if not self.check_key_exists(key_name):
                logger.warning("Attempting to publish with non-existent key: %s. This may fail.", key_name)

            publish_result = self.client.name.publish(path_to_publish, key=key_name, lifetime=lifetime)
            logger.info("Published %s to IPNS name %s (key: %s)", path_to_publish, publish_result['Name'], key_name)
            return publish_result
        except Exception as e:
            logger.error("Failed to publish CID %s to IPNS using key %s: %s", cid, key_name, e)
            raise

    def resolve_ipns_name(self, ipns_name: str) -> str:
        """Resolve an IPNS name to its currently published IPFS path."""
        if not ipns_name.startswith("/ipns/"):
            raise ValueError("IPNS name must start with /ipns/")
        try:
            resolved = self.client.name.resolve(ipns_name)

            resolved_path = resolved['Path']
            logger.info("Resolved IPNS name %s to %s", ipns_name, resolved_path)
            return resolved_path
        except ipfshttpclient.exceptions.ErrorResponse as e:
            if "could not resolve name" in str(e) or "record not found" in str(e) :
                logger.warning("Could not resolve IPNS name %s: %s", ipns_name, e)
                raise FileNotFoundError(f"Could not resolve IPNS name {ipns_name}. It may not exist or not be propagated yet.") from e
            logger.error("Error resolving IPNS name %s: %s", ipns_name, e)
            raise
        except Exception as e:
            logger.error("Unexpected error resolving IPNS name %s: %s", ipns_name, e)
            raise

    def get_pinned_cids(self) -> set[str]:
        """Retrieve a set of all CIDs currently pinned by the local IPFS node."""
        try:
            pinned_items = self.client.pin.ls(type='recursive')
            cids = set(pinned_items.get('Keys', {}).keys())
            logger.info("Retrieved %d pinned CIDs from the local node.", len(cids))
            return cids
        except ipfshttpclient.exceptions.ErrorResponse as e:
            logger.error(f"IPFS Error retrieving pinned CIDs: {e}")
            return set()
        except Exception as e:
            logger.error("Failed to retrieve pinned CIDs: %s", e, exc_info=True)
            # Return an empty set on error to allow dependant commands to function gracefully
            return set()

    def find_providers(self, cid: str, timeout: int = 60) -> Set[str]:
        """Find peers providing a given CID.

        Attempts to use the client API first. If that fails due to specific known
        API deprecation errors (e.g., on older daemons), it falls back to calling
        the `ipfs routing findprovs` command via subprocess.
        """
        providers = set()
        primary_method_failed_due_to_api = False

        # --- Primary Method: Use ipfshttpclient API --- 
        try:
            logger.info(f"Attempting API call dht.findprovs for CID {cid} (timeout={timeout}s)...")
            provs_stream = self.client.dht.findprovs(cid, timeout=timeout)
            
            for prov_info in provs_stream:
                if isinstance(prov_info, dict) and prov_info.get('Type') == 4:
                    responses = prov_info.get('Responses')
                    if isinstance(responses, list):
                        for peer_data in responses:
                            if isinstance(peer_data, dict) and 'ID' in peer_data:
                                providers.add(peer_data['ID'])
            
            if not providers:
                 logger.info(f"API call: No providers found for CID {cid} within the timeout.")
            else:
                 logger.info(f"API call: Found {len(providers)} providers for CID {cid}.")
            return providers # Success with primary method

        except ipfshttpclient.exceptions.TimeoutError:
             logger.warning(f"Timeout occurred after {timeout} seconds during API call dht.findprovs for CID {cid}.")
             # Do not fall back on timeout, as the command line might also timeout
        except ipfshttpclient.exceptions.ErrorResponse as e:
             error_str = str(e).lower()
             # Check for specific error messages indicating the API is deprecated/removed
             if "use 'ipfs routing' instead" in error_str or "no command found" in error_str:
                 logger.warning(f"API call dht.findprovs failed for CID {cid} (likely unsupported by daemon). Will attempt fallback using `ipfs routing findprovs` CLI command. Error: {e}")
                 primary_method_failed_due_to_api = True # Signal that fallback should be tried
             elif "routing: not found" in error_str:
                 logger.warning(f"API call: Could not find providers for CID {cid} (likely not available on the network): {e}")
                 # Content not found via API, unlikely CLI will find it either, don't fallback.
             else:
                 logger.error(f"IPFS error response during API call dht.findprovs for CID {cid}: {e}")
                 # Unknown API error, might not be recoverable by CLI fallback.
        except Exception as e:
            logger.error(f"Unexpected error during API call dht.findprovs for CID {cid}: {e}", exc_info=True)
            # Unexpected API error, might not be recoverable by CLI fallback.

        # --- Fallback Method: Use `ipfs routing findprovs` CLI command --- 
        if primary_method_failed_due_to_api:
            logger.info(f"Attempting fallback using `ipfs routing findprovs {cid}` CLI command...")
            try:
                # Use a timeout for the subprocess as well, slightly less than the main timeout?
                # Note: subprocess timeout is for the whole command execution.
                cli_timeout = max(5, timeout - 5) # Give some buffer
                result = subprocess.run(
                    ["ipfs", "routing", "findprovs", cid],
                    capture_output=True,
                    text=True,
                    check=False, # Don't raise exception on non-zero exit code immediately
                    timeout=cli_timeout
                )
                
                if result.returncode == 0:
                    output_lines = result.stdout.strip().split('\n')
                    for line in output_lines:
                        peer_id = line.strip()
                        if peer_id: # Basic validation: non-empty string
                           # Could add more robust Peer ID validation if needed (e.g., starts with Qm or 12D)
                           providers.add(peer_id)
                    logger.info(f"CLI Fallback: Found {len(providers)} providers for CID {cid}.")
                    return providers # Success with fallback
                else:
                    # Command failed
                    stderr_output = result.stderr.strip()
                    logger.error(f"CLI fallback command `ipfs routing findprovs {cid}` failed (exit code {result.returncode}). Stderr: {stderr_output}")
            
            except FileNotFoundError:
                logger.error("CLI fallback failed: 'ipfs' command not found in PATH. Cannot execute `ipfs routing findprovs`.")
            except subprocess.TimeoutExpired:
                logger.error(f"CLI fallback command `ipfs routing findprovs {cid}` timed out after {cli_timeout} seconds.")
            except Exception as e:
                logger.error(f"Unexpected error during CLI fallback execution for CID {cid}: {e}", exc_info=True)

        # If we reach here, both primary and (if attempted) fallback methods failed.
        logger.warning(f"Could not determine providers for CID {cid} using API or CLI fallback.")
        return set() # Return empty set indicating failure

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
        """Returns the Peer ID of the connected IPFS node."""
        if self.client_id_dict:
            return self.client_id_dict.get('ID')
        
        # Fallback if ipfshttpclient connection failed but go_wrapper might work
        if not self.client and self.is_go_wrapper_available():
            try:
                logger.info("Attempting to get Peer ID via Go wrapper as fallback...")
                # Assuming the Go wrapper's 'id' command outputs JSON similar to 'ipfs id'
                id_info = self._execute_go_wrapper_command_json("id")
                peer_id = id_info.get("ID")
                if peer_id:
                    logger.info(f"Successfully retrieved Peer ID via Go wrapper: {peer_id}")
                    # Cache it if desired, though self.client_id_dict is usually from http client
                    # self.client_id_dict = id_info 
                    return peer_id
                else:
                    logger.warning("Go wrapper 'id' command did not return an 'ID' field in data.")
                    return None
            except SciPFSGoWrapperError as e:
                logger.warning(f"Go wrapper 'id' command failed: {e}")
                return None
            except Exception as e:
                logger.warning(f"An unexpected error occurred trying to get Peer ID via Go wrapper: {e}")
                return None
        
        logger.warning("Could not determine local Peer ID via ipfshttpclient or Go wrapper fallback.")
        return None

    def _execute_go_wrapper_command_json(self, go_command: str, *args: str) -> Dict:
        """Execute a Go wrapper command that is expected to return JSON and parse it."""
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
            logger.debug(f"Executing Go wrapper command: {' '.join(command)}")
            # Using a moderate timeout, adjust if specific commands are known to be long-running
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)

            if result.returncode == 0:
                try:
                    response_json = json.loads(result.stdout)
                    if response_json.get("success"):
                        # Assuming successful responses place their payload in "data"
                        return response_json.get("data", {})
                    else:
                        error_msg = response_json.get("error", f"Unknown error from Go wrapper's {go_command}")
                        logger.error(f"Go wrapper command '{go_command}' failed: {error_msg}. stdout: {result.stdout.strip()}")
                        raise SciPFSGoWrapperError(f"Go wrapper command '{go_command}' failed: {error_msg}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON response from Go wrapper for {go_command}. stdout: {result.stdout.strip()}")
                    raise SciPFSGoWrapperError(f"Failed to decode JSON from Go wrapper for {go_command}")
            else:
                error_detail = result.stderr.strip()
                try:
                    error_json = json.loads(error_detail)
                    error_detail = error_json.get("error", error_detail)
                except json.JSONDecodeError:
                    pass # Use raw stderr if not JSON
                logger.error(f"Go wrapper command '{go_command}' failed with exit code {result.returncode}. Stderr: {error_detail}")
                raise SciPFSGoWrapperError(f"Go wrapper command '{go_command}' failed with exit {result.returncode}: {error_detail}")
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
