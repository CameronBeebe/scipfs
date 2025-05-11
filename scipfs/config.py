import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".scipfs"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "username": None
}

def load_config() -> dict:
    """Loads the configuration from the config file."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy() # Return default if no config file
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            # Ensure default keys exist
            full_config = DEFAULT_CONFIG.copy()
            full_config.update(config)
            return full_config
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error loading config file {CONFIG_FILE}: {e}. Returning default config.")
        return DEFAULT_CONFIG.copy()

def save_config(config: dict) -> None:
    """Saves the configuration dictionary to the config file."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        logger.error(f"Error saving config file {CONFIG_FILE}: {e}")
        raise # Re-raise the exception for the CLI to handle

def get_username() -> str | None:
    """Convenience function to get the configured username."""
    return load_config().get("username")

def set_username(username: str) -> None:
    """Sets the username in the configuration."""
    config = load_config()
    config["username"] = username
    save_config(config) 