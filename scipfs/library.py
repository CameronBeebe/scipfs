import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from .ipfs import IPFSClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Library:
    """Manages a decentralized file library on IPFS."""
    
    def __init__(self, name: str, config_dir: Path, ipfs_client: IPFSClient):
        """Initialize a library with a name and configuration directory."""
        self.name = name
        self.config_dir = config_dir
        self.ipfs_client = ipfs_client
        self.manifest_path = config_dir / f"{name}_manifest.json"
        self.manifest: Dict = {"name": name, "files": {}}
        self.manifest_cid: Optional[str] = None
        self.ipns_key_name: Optional[str] = None # For the key used to publish
        self.ipns_name: Optional[str] = None     # The /ipns/... address
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load the manifest from local storage or initialize a new one in memory."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r") as f:
                    self.manifest = json.load(f)
                self.name = self.manifest.get("name", self.name) # Ensure name is consistent
                self.manifest_cid = self.manifest.get("latest_manifest_cid") # If we store it
                self.ipns_key_name = self.manifest.get("ipns_key_name")
                self.ipns_name = self.manifest.get("ipns_name")
                logger.info("Loaded manifest for library %s from %s", self.name, self.manifest_path)
            except json.JSONDecodeError:
                logger.error("Manifest file %s is corrupted. Initializing empty manifest in memory.", self.manifest_path)
                self.manifest = {"name": self.name, "files": {}}
                self.manifest_cid = None
                self.ipns_key_name = None
                self.ipns_name = None
        else:
            self.manifest = {"name": self.name, "files": {}}
            self.manifest_cid = None
            self.ipns_key_name = None
            self.ipns_name = None
            logger.info("Initialized new manifest structure in memory for library %s (not saved yet)", self.name)

    def _save_manifest(self) -> None:
        """Save the manifest locally, update its IPFS CID, and publish to IPNS if key is available."""
        # Ensure current IPNS info is in the manifest dict before saving to IPFS
        if self.ipns_key_name:
            self.manifest["ipns_key_name"] = self.ipns_key_name
        if self.ipns_name:
            self.manifest["ipns_name"] = self.ipns_name
        
        # Add the potentially updated manifest (with IPNS info) to IPFS
        current_manifest_cid = self.ipfs_client.add_json(self.manifest)
        self.manifest_cid = current_manifest_cid
        self.manifest["latest_manifest_cid"] = current_manifest_cid # Store the latest CID in manifest
        
        # Save the manifest with all info (including latest_manifest_cid) locally
        with open(self.manifest_path, "w") as f:
            json.dump(self.manifest, f, indent=2)
        
        logger.info("Saved manifest locally for library %s at %s", self.name, self.manifest_path)
        logger.info("Current manifest CID for %s is %s", self.name, self.manifest_cid)
        
        # Pin the new manifest CID
        self.ipfs_client.pin(self.manifest_cid)
        logger.info("Pinned manifest CID %s for library %s", self.manifest_cid, self.name)

        # Publish to IPNS if this instance owns the key
        if self.ipns_key_name and self.manifest_cid:
            try:
                self.ipfs_client.publish_to_ipns(self.ipns_key_name, self.manifest_cid)
                logger.info("Published manifest CID %s to IPNS for key %s (IPNS Name: %s)", 
                            self.manifest_cid, self.ipns_key_name, self.ipns_name)
            except Exception as e:
                # Log error but don't let publish failure stop the whole save process
                logger.error("Failed to publish manifest to IPNS for key %s: %s", self.ipns_key_name, e)
        else:
            logger.debug("Not publishing to IPNS: ipns_key_name not set or manifest_cid missing.")

    def create(self) -> None:
        """Create a new library, generate an IPNS key, save manifest, and publish to IPNS."""
        if self.manifest_path.exists():
            raise ValueError(f"Library configuration file {self.manifest_path} already exists.")

        self.ipns_key_name = self.name # Use library name as the IPNS key name
        
        try:
            logger.info("Attempting to generate/retrieve IPNS key: %s", self.ipns_key_name)
            key_info = self.ipfs_client.generate_ipns_key(self.ipns_key_name)
            # key_info is {'Name': name, 'Id': peer_id}
            self.ipns_name = f"/ipns/{key_info['Id']}"
            self.manifest["ipns_key_name"] = self.ipns_key_name
            self.manifest["ipns_name"] = self.ipns_name
            logger.info("Library %s will be addressable via IPNS name: %s (using key: %s)", 
                        self.name, self.ipns_name, self.ipns_key_name)
            
            # Initial save and publish
            self._save_manifest() # This will add to IPFS, pin, save locally, and publish
            logger.info("Successfully created library %s, initial manifest CID %s, IPNS name %s",
                        self.name, self.manifest_cid, self.ipns_name)

        except Exception as e:
            logger.error("Failed to create library %s with IPNS integration: %s", self.name, e)
            if self.manifest_path.exists():
                try:
                    self.manifest_path.unlink()
                    logger.info("Cleaned up partially created manifest file %s", self.manifest_path)
                except OSError as unlink_e:
                     logger.error("Failed to clean up manifest file %s: %s", self.manifest_path, unlink_e)
            raise

    def join(self, ipns_name_to_join: str) -> None:
        """Join an existing library by its IPNS name."""
        if not ipns_name_to_join.startswith("/ipns/"):
            raise ValueError("Invalid IPNS name format. Must start with /ipns/")

        logger.info("Attempting to join library via IPNS name: %s", ipns_name_to_join)
        try:
            resolved_path = self.ipfs_client.resolve_ipns_name(ipns_name_to_join)
            if not resolved_path or not resolved_path.startswith("/ipfs/"):
                raise ValueError(f"IPNS name {ipns_name_to_join} resolved to an invalid path: {resolved_path}")
            
            manifest_cid_from_ipns = resolved_path.split("/ipfs/")[-1]
            logger.info("IPNS name %s resolved to manifest CID: %s", ipns_name_to_join, manifest_cid_from_ipns)

            self.manifest = self.ipfs_client.get_json(manifest_cid_from_ipns)
            
            # Update library instance attributes from the fetched manifest
            self.name = self.manifest.get("name")
            if not self.name:
                # If manifest has no name, try to derive from IPNS or a default
                # For now, this case should ideally not happen if manifest is well-formed
                raise ValueError("Manifest fetched from IPNS is missing a 'name' field.")

            self.manifest_path = self.config_dir / f"{self.name}_manifest.json" # Update path based on new name
            self.manifest_cid = manifest_cid_from_ipns # This is the CID of the manifest we just fetched
            
            # Store the IPNS name we joined, but NOT the key_name (as we don't own the key)
            self.ipns_name = ipns_name_to_join
            self.manifest["ipns_name"] = self.ipns_name 
            # Ensure no ipns_key_name is spuriously carried over or set if not owned
            self.ipns_key_name = self.manifest.get("ipns_key_name") # Load it if present
            # If the manifest *downloaded* via IPNS has an ipns_key_name from its original creator,
            # we should *not* adopt it as our own key for publishing.
            # So, when saving locally after a join, ensure this instance's ipns_key_name is cleared
            # if this node isn't the original creator.
            # The logic in _save_manifest handles this: it only publishes if self.ipns_key_name is set.
            # For a joined library, self.ipns_key_name should remain None or be explicitly cleared before save.
            # Let's clear it here to be safe, so _save_manifest doesn't try to publish.
            if self.manifest.get("ipns_key_name") and self.manifest.get("ipns_key_name") != self.name: # Heuristic
                 self.manifest.pop("ipns_key_name", None) # Remove if it's not "ours"
            self.ipns_key_name = None # This instance joining does not own the key by default.

            # Save the fetched manifest locally. This will also pin the manifest_cid.
            # Crucially, _save_manifest will NOT attempt to publish to IPNS because self.ipns_key_name is None.
            self._save_manifest() 
            logger.info("Successfully joined and saved manifest for library %s from IPNS name %s (Manifest CID: %s)",
                        self.name, self.ipns_name, self.manifest_cid)

        except FileNotFoundError: # Raised by resolve_ipns_name if it can't be resolved
             logger.error("Failed to join library: IPNS name %s could not be resolved.", ipns_name_to_join)
             raise
        except Exception as e:
            logger.error("Failed to join library with IPNS name %s: %s", ipns_name_to_join, e)
            raise

    def add_file(self, file_path: Path, username: str) -> None:
        """Add a file to the library and update the manifest, including the adder."""
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        cid = self.ipfs_client.add_file(file_path)
        self.ipfs_client.pin(cid)
        self.manifest["files"][file_path.name] = {
            "cid": cid,
            "size": file_path.stat().st_size,
            "added_timestamp": file_path.stat().st_mtime, # Keep timestamp
            "added_by": username # Store the username
        }
        self._save_manifest()
        logger.info("Added file %s to library %s by %s", file_path.name, self.name, username)

    def list_files(self) -> List[Dict]:
        """List all files in the library."""
        # Ensure structure includes new field even if missing in older manifests (optional)
        files_list = []
        for name, details in self.manifest.get("files", {}).items():
             file_info = {
                 "name": name,
                 "cid": details.get("cid"),
                 "size": details.get("size"),
                 "added_timestamp": details.get("added_timestamp"),
                 "added_by": details.get("added_by") # Safely get username
             }
             files_list.append(file_info)
        return files_list

    def get_file(self, file_name: str, output_path: Path) -> None:
        """Download a file from the library by name."""
        if file_name not in self.manifest["files"]:
            raise KeyError(f"File {file_name} not found in library {self.name}")
        cid = self.manifest["files"][file_name]["cid"]
        self.ipfs_client.get_file(cid, output_path)
