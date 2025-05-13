import ipfshttpclient
import logging
from pathlib import Path
from typing import Dict, Optional, List, Set
import json
import subprocess # Import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IPFSClient:
    """Manages interactions with an IPFS node."""
    
    def __init__(self, addr: str = "/ip4/127.0.0.1/tcp/5001"):
        """Initialize IPFS client with the given node address."""
        try:
            self.client = ipfshttpclient.connect(addr, timeout=30)
            self.client.id()
            logger.info("Successfully connected to IPFS node at %s", addr)
        except ipfshttpclient.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to IPFS node at {addr}. Is the IPFS daemon running? {e}")
            raise ConnectionError(f"Could not connect to IPFS node at {addr}. Please ensure the IPFS daemon is running.") from e
        except Exception as e:
            logger.error("Failed to connect to IPFS node: %s", e)
            raise ConnectionError(f"Could not connect to IPFS node at {addr}: {e}")

    def add_file(self, file_path: Path) -> str:
        """Add a file to IPFS and return its CID."""
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        try:
            result = self.client.add(str(file_path))
            cid = result["Hash"]
            logger.info("Added file %s to IPFS with CID %s", file_path, cid)
            return cid
        except Exception as e:
            logger.error("Failed to add file %s: %s", file_path, e)
            raise

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
        """Pin a CID to ensure it remains available."""
        try:
            self.client.pin.add(cid)
            logger.info("Pinned CID %s", cid)
        except Exception as e:
            logger.error("Failed to pin CID %s: %s", cid, e)
            raise

    def get_json(self, cid: str) -> Dict:
        """Retrieve and parse JSON content from IPFS by CID."""
        try:
            content = self.client.cat(cid).decode("utf-8")
            return json.loads(content)
        except Exception as e:
            logger.error("Failed to retrieve JSON for CID %s: %s", cid, e)
            raise

    def add_json(self, data: Dict) -> str:
        """Add JSON data to IPFS and return its CID."""
        try:
            res = self.client.add_json(data)
            cid = res if isinstance(res, str) else res.get('Hash')
            if not cid:
                raise ValueError("Failed to get CID from add_json response")
            logger.info("Added JSON to IPFS with CID %s", cid)
            return cid
        except Exception as e:
            logger.error("Failed to add JSON: %s", e)
            raise

    def generate_ipns_key(self, key_name: str) -> Dict:
        """Generate a new IPNS key pair."""
        try:
            key_info = self.client.key.gen(key_name, type="rsa", size=2048)
            logger.info("Generated IPNS key '%s' with ID %s", key_info['Name'], key_info['Id'])
            return key_info
        except ipfshttpclient.exceptions.ErrorResponse as e:
            if "key with name already exists" in str(e):
                logger.warning("IPNS key '%s' already exists. Will attempt to use existing key.", key_name)
                keys = self.list_ipns_keys()
                for key in keys:
                    if key['Name'] == key_name:
                        return key
                raise ValueError(f"Key '{key_name}' reported as existing but not found in list.") from e
            logger.error("Failed to generate IPNS key '%s': %s", key_name, e)
            raise

    def list_ipns_keys(self) -> List[Dict]:
        """List all IPNS keys in the keystore."""
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
