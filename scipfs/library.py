import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from .ipfs import IPFSClient, SciPFSFileNotFoundError

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
        self.manifest: Dict[str, Any] = {"name": name, "files": {}}  # Initialize with proper structure
        self.manifest_path = config_dir / f"{name}_manifest.json"
        self.manifest_cid: Optional[str] = None
        self.ipns_name: Optional[str] = None
        self.ipns_key_name: Optional[str] = None
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load the manifest from local storage or initialize a new one in memory."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r") as f:
                    loaded_data = json.load(f)
                
                self.manifest_cid = loaded_data.pop("local_manifest_cid", None) # Pop it out, store it
                self.manifest = loaded_data # The rest is the actual manifest

                self.name = self.manifest.get("name", self.name) # Ensure name is consistent
                self.ipns_key_name = self.manifest.get("ipns_key_name")
                self.ipns_name = self.manifest.get("ipns_name")
                # self.manifest_cid is now loaded from the file if it was there
                logger.info("Loaded manifest for library %s from %s (Local CID: %s)", self.name, self.manifest_path, self.manifest_cid)

            except json.JSONDecodeError:
                logger.error("Manifest file %s is corrupted. Initializing empty manifest in memory.", self.manifest_path)
                self.manifest = {"name": self.name, "files": {}}
                self.manifest_cid = None
                self.ipns_key_name = None
                self.ipns_name = None
            except Exception as e: # Catch other potential errors like file not found during open, though exists() checks first
                logger.error("Failed to load manifest %s: %s. Initializing empty manifest.", self.manifest_path, e)
                self.manifest = {"name": self.name, "files": {}}
                self.manifest_cid = None
                self.ipns_key_name = None
                self.ipns_name = None
        else:
            self.manifest = {"name": self.name, "files": {}}
            self.manifest_cid = None # Explicitly None for a new, non-existent manifest
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
        
        # Add the core manifest (without its own CID yet) to IPFS to get its true CID
        # This self.manifest should NOT contain 'local_manifest_cid' at this point.
        current_manifest_cid = self.ipfs_client.add_json(self.manifest)
        self.manifest_cid = current_manifest_cid # This is the CID of the content in self.manifest
        
        # Prepare data for local JSON file, including the local_manifest_cid
        manifest_to_save_locally = self.manifest.copy()
        if self.manifest_cid: # Only add if a CID was successfully generated
            manifest_to_save_locally["local_manifest_cid"] = self.manifest_cid
        
        # Save the manifest with all info (including its own CID) locally
        with open(self.manifest_path, "w") as f:
            json.dump(manifest_to_save_locally, f, indent=2)
        
        logger.info("Saved manifest locally for library %s at %s (CID: %s)", self.name, self.manifest_path, self.manifest_cid)
        # logger.info("Current manifest CID for %s is %s", self.name, self.manifest_cid) # Redundant with above
        
        # Pin the new manifest CID (content CID)
        if self.manifest_cid: # Ensure there's a CID to pin
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
            manifest_name = self.manifest.get("name")
            if not manifest_name:
                # If manifest has no name, try to derive from IPNS or a default
                # For now, this case should ideally not happen if manifest is well-formed
                raise ValueError("Manifest fetched from IPNS is missing a 'name' field.")
            
            self.name = manifest_name  # Now we're assigning a str to str
            self.manifest_path = self.config_dir / f"{self.name}_manifest.json" # Update path based on new name
            self.manifest_cid = manifest_cid_from_ipns # This is the CID of the manifest we just fetched
            
            # Store the IPNS name we joined, but NOT the key_name (as we don't own the key)
            self.ipns_name = ipns_name_to_join
            self.manifest["ipns_name"] = self.ipns_name 
            # Ensure no ipns_key_name is spuriously carried over or set if not owned
            if "ipns_key_name" in self.manifest:
                logger.debug(f"Manifest downloaded for join from {self.ipns_name} contained an ipns_key_name: {self.manifest['ipns_key_name']}. This will be ignored for the joining node.")
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
            raise SciPFSFileNotFoundError(f"File not found: {file_path}")
        cid = self.ipfs_client.add_file(file_path)
        self.ipfs_client.pin(cid)
        self.manifest["files"][file_path.name] = {
            "cid": cid,
            "size": file_path.stat().st_size,
            "added_timestamp": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
            "added_by": username
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

    def get_file_info(self, file_name: str) -> Optional[Dict]:
        """Get information about a specific file in the library."""
        file_details = self.manifest.get("files", {}).get(file_name)
        if file_details:
            return {
                "name": file_name,
                "cid": file_details.get("cid"),
                "size": file_details.get("size"),
                "added_timestamp": file_details.get("added_timestamp"),
                "added_by": file_details.get("added_by")
            }
        return None

    def update_from_ipns(self) -> bool:
        """Update the local library manifest by fetching the latest from its IPNS name.
        
        Returns:
            bool: True if the manifest was updated, False otherwise.
        """
        if not self.ipns_name:
            logger.warning("Cannot update library '%s': No IPNS name is associated with the local manifest.", self.name)
            raise ValueError("Library does not have an IPNS name for updates.")

        logger.info("Attempting to update library '%s' from IPNS name: %s", self.name, self.ipns_name)
        
        try:
            resolved_path = self.ipfs_client.resolve_ipns_name(self.ipns_name)
            if not resolved_path or not resolved_path.startswith("/ipfs/"):
                logger.error("IPNS name %s for library '%s' resolved to an invalid path: %s", 
                             self.ipns_name, self.name, resolved_path)
                raise FileNotFoundError(f"IPNS name {self.ipns_name} resolved to an invalid path: {resolved_path}")
            
            new_manifest_cid = resolved_path.split("/ipfs/")[-1]
            logger.info("IPNS name %s for library '%s' resolved to new manifest CID: %s", 
                        self.ipns_name, self.name, new_manifest_cid)

            # If self.manifest_cid is None (e.g. new local lib just created but not saved from ipns)
            # or if new CID is different, then update.
            if self.manifest_cid != new_manifest_cid:
                logger.info("Current manifest CID for '%s' is '%s'. New manifest CID is '%s'. Updating...",
                            self.name, self.manifest_cid, new_manifest_cid)
                
                new_manifest_data = self.ipfs_client.get_json(new_manifest_cid)
                
                # Potentially validate new_manifest_data structure here
                if not isinstance(new_manifest_data, dict) or "name" not in new_manifest_data or "files" not in new_manifest_data:
                    logger.error("Fetched manifest for CID %s is malformed: %s", new_manifest_cid, new_manifest_data)
                    raise ValueError(f"Fetched manifest from {new_manifest_cid} is malformed.")

                original_name = self.name
                self.manifest = new_manifest_data
                self.name = self.manifest.get("name", original_name) # Update name if changed
                
                if self.name != original_name:
                    logger.info("Library name changed from '%s' to '%s' during update. Updating manifest path.",
                                original_name, self.name)
                    self.manifest_path = self.config_dir / f"{self.name}_manifest.json"
                    # If name changes, the old manifest file for original_name might be left behind.
                    # Consider if cleanup is needed, or if it's acceptable. For now, it will just save with new name.

                self.manifest_cid = new_manifest_cid
                
                # Important: This node is just updating/following. It does not become the owner.
                # So, ensure ipns_key_name is not adopted from the fetched manifest for publishing purposes.
                # self.ipns_key_name should remain as it was (likely None if this is a joined library).
                # _save_manifest already correctly handles not publishing if self.ipns_key_name is not set.
                # If the fetched manifest *contains* an 'ipns_key_name' from the original publisher,
                # it will be saved in the local JSON, which is fine for informational purposes.
                # The critical part is that `self.ipns_key_name` on the *object* is not changed to that value.
                
                self._save_manifest() # This will save locally and pin. It will NOT republish if self.ipns_key_name is not set.
                logger.info("Library '%s' successfully updated to manifest CID %s. Local manifest saved.",
                            self.name, self.manifest_cid)
                return True
            else:
                logger.info("Library '%s' is already up-to-date. Manifest CID: %s", self.name, self.manifest_cid)
                return False

        except FileNotFoundError: # From resolve_ipns_name
             logger.error("Failed to update library '%s': IPNS name %s could not be resolved.", self.name, self.ipns_name)
             raise
        except Exception as e:
            logger.error("Failed to update library '%s' from IPNS: %s", self.name, e, exc_info=True)
            raise
