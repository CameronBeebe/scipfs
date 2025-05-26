import json
import logging
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class SciPFSConfig:
    """Manages SciPFS configuration stored in a JSON file."""

    def __init__(self, config_dir: Path):
        """Initialize configuration manager.

        Args:
            config_dir: The directory where configuration files are stored (~/.scipfs).
        """
        self.config_dir = config_dir
        # Ensure the directory exists before trying to access files within it
        self.config_dir.mkdir(parents=True, exist_ok=True) 
        self.config_file_path = self.config_dir / "config.json"
        self.config_data: Dict = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from the JSON file.

        Handles file not found and JSON decoding errors.
        """
        if self.config_file_path.exists():
            try:
                with open(self.config_file_path, "r") as f:
                    self.config_data = json.load(f)
                if not isinstance(self.config_data, dict):
                     logger.warning(f"Config file {self.config_file_path} does not contain a valid JSON object. Resetting.")
                     self.config_data = {}
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from config file {self.config_file_path}. File might be corrupted. Resetting config.", exc_info=True)
                self.config_data = {}
            except Exception as e:
                 logger.error(f"Failed to load config file {self.config_file_path}: {e}", exc_info=True)
                 self.config_data = {} # Reset on other load errors
        else:
            logger.debug(f"Config file {self.config_file_path} not found. Initializing empty config.")
            self.config_data = {}

    def _save_config(self) -> None:
        """Save the current configuration data to the JSON file."""
        try:
            # Ensure directory exists again just in case
            self.config_dir.mkdir(parents=True, exist_ok=True) 
            with open(self.config_file_path, "w") as f:
                json.dump(self.config_data, f, indent=4)
            logger.debug(f"Saved configuration to {self.config_file_path}")
        except Exception as e:
            logger.error(f"Failed to save config file {self.config_file_path}: {e}", exc_info=True)

    def get_username(self) -> Optional[str]:
        """Get the configured username.

        Returns:
            The username string or None if not set.
        """
        return self.config_data.get("username")

    def set_username(self, username: str) -> None:
        """Set the username in the configuration and save it.

        Args:
            username: The username string to set.
        """
        if not isinstance(username, str) or not username:
            raise ValueError("Username must be a non-empty string.")
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        self.config_data["username"] = username
        self._save_config()

    def get_api_addr_for_client(self) -> str:
        """Get the configured IPFS API multiaddress.

        Returns:
            The IPFS API multiaddress string, or a default if not set.
        """
        return self.config_data.get("ipfs_api_addr", "/ip4/127.0.0.1/tcp/5001")

    def set_api_addr(self, api_addr: str) -> None:
        """Set the IPFS API multiaddress in the configuration and save it.

        Args:
            api_addr: The IPFS API multiaddress string to set (e.g., "/ip4/127.0.0.1/tcp/5001").
        """
        # Basic validation could be added here if desired (e.g., check if it starts with /ip4 or /dns)
        if not isinstance(api_addr, str) or not api_addr:
            raise ValueError("IPFS API address must be a non-empty string.")
        self.config_data["ipfs_api_addr"] = api_addr
        self._save_config()
        logger.info(f"IPFS API address set to: {api_addr}")

    # --- Future methods for other config settings can be added below ---
    # Example:
    # def get_reputable_peers(self) -> List[Dict]:
    #     return self.config_data.get("reputable_peers", [])
    #
    # def add_reputable_peer(self, peer_id: str, alias: str) -> None:
    #     peers = self.get_reputable_peers()
    #     # Avoid duplicates
    #     if not any(p.get('id') == peer_id for p in peers):
    #         peers.append({"id": peer_id, "alias": alias})
    #         self.config_data["reputable_peers"] = peers
    #         self._save_config() 