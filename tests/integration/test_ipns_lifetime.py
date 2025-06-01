import unittest
import subprocess
import sys
import os
from pathlib import Path
import json
import time # For potential cleanup delays or IPNS propagation
import re

# Add project root to sys.path to allow importing scipfs modules if needed
# (though for CLI testing, direct subprocess calls are primary)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Helper function to run scipfs commands
def run_scipfs_command(command_args, timeout=60):
    # Try to use the editable install first, then fallback to installed scipfs
    # This assumes the tests are run from the project root or similar context
    # where 'python -m scipfs.cli' would work for an editable install.
    try:
        base_command = [sys.executable, "-m", "scipfs.cli"]
        # Quick check if this module path might work (doesn't guarantee scipfs is runnable this way)
        # A more robust check might involve trying to import scipfs.cli
        subprocess.run(base_command + ["--version"], capture_output=True, text=True, check=True, timeout=5)
        print(f"Using 'python -m scipfs.cli' for commands.")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        print(f"Falling back to 'scipfs' command (assuming it's in PATH).")
        base_command = ["scipfs"]
        try:
            subprocess.run(base_command + ["--version"], capture_output=True, text=True, check=True, timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            print(f"CRITICAL: Neither 'python -m scipfs.cli' nor 'scipfs' command seem to work. Ensure scipfs is installed and accessible.")
            print(f"Details: {e}")
            # This is a fatal error for the test setup
            raise RuntimeError("SciPFS command not found or not executable.") from e


    full_command = base_command + command_args
    print(f"Executing: {' '.join(full_command)}") # For test visibility
    try:
        result = subprocess.run(full_command, capture_output=True, text=True, check=False, timeout=timeout)
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        return result
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds: {' '.join(full_command)}")
        # Create a mock result object for timeout
        return subprocess.CompletedProcess(args=full_command, returncode=124, stdout="TIMEOUT", stderr="Command timed out")
    except Exception as e:
        print(f"Error running command {' '.join(full_command)}: {e}")
        raise

# Helper to remove IPNS key (assumes 'ipfs' CLI is in PATH)
def remove_ipfs_key(key_name):
    try:
        print(f"Attempting to remove IPFS key: {key_name}")
        # First, check if key exists to avoid error if it doesn't
        list_cmd = ["ipfs", "key", "list"]
        list_res = subprocess.run(list_cmd, capture_output=True, text=True, check=False, timeout=10)
        key_found = False
        if list_res.returncode == 0:
            for line in list_res.stdout.splitlines():
                if key_name in line.split(): # Simple check, might be fragile if key_name is substring of another
                    # A more precise check: parts = line.split(); if len(parts) >=2 and parts[1] == key_name:
                    key_found = True
                    break
        
        if key_found:
            cmd = ["ipfs", "key", "rm", key_name]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
            if res.returncode == 0:
                print(f"Successfully removed IPFS key: {key_name}")
            else:
                print(f"Warning: Failed to remove IPFS key {key_name}. Stderr: {res.stderr.strip()}")
        else:
            print(f"IPFS key {key_name} not found, skipping removal.")
            
    except subprocess.TimeoutExpired:
        print(f"Warning: Timeout during IPFS key removal for {key_name}")
    except Exception as e:
        print(f"Warning: Exception during IPFS key removal for {key_name}: {e}")

class TestIPNSLifetime(unittest.TestCase):
    CONFIG_DIR = Path.home() / ".scipfs"
    TEST_USERNAME = "pytest_user_lt" # Unique username for these tests
    LIB_DEFAULT_LIFETIME_NAME = "testlib_default_lt"
    LIB_CUSTOM_LIFETIME_NAME = "testlib_custom_lt"
    CUSTOM_LIFETIME_VAL = "48h" # Different from default 24h
    DEFAULT_LIFETIME_VAL = "24h"

    @classmethod
    def setUpClass(cls):
        print(f"--- TestIPNSLifetime: setUpClass ---")
        # Clean up any previous test runs first to ensure a clean state
        cls._clean_up_resources()
        
        res = run_scipfs_command(["config", "set", "username", cls.TEST_USERNAME])
        if res.returncode != 0 and "already set" not in res.stdout.lower() and "set to" not in res.stdout.lower():
             print(f"Warning: Failed to set username for tests. STDOUT: {res.stdout} STDERR: {res.stderr}")
        
        print("Please ensure your IPFS daemon is running for these integration tests.")
        # Give a small delay for IPFS to be ready if it was just started
        time.sleep(2)


    @classmethod
    def tearDownClass(cls):
        print(f"--- TestIPNSLifetime: tearDownClass ---")
        cls._clean_up_resources()

    @classmethod
    def _clean_up_resources(cls):
        print("Cleaning up test resources...")
        manifest_default = cls.CONFIG_DIR / f"{cls.LIB_DEFAULT_LIFETIME_NAME}_manifest.json"
        manifest_custom = cls.CONFIG_DIR / f"{cls.LIB_CUSTOM_LIFETIME_NAME}_manifest.json"
        
        if manifest_default.exists():
            print(f"Removing manifest: {manifest_default}")
            manifest_default.unlink()
        if manifest_custom.exists():
            print(f"Removing manifest: {manifest_custom}")
            manifest_custom.unlink()
            
        remove_ipfs_key(cls.LIB_DEFAULT_LIFETIME_NAME)
        remove_ipfs_key(cls.LIB_CUSTOM_LIFETIME_NAME)
        print("Finished cleaning up test resources.")


    def test_01_create_library_default_lifetime(self):
        print(f"\n--- Test: Create Library with Default Lifetime ({self.LIB_DEFAULT_LIFETIME_NAME}) ---")
        args = ["--verbose", "create", self.LIB_DEFAULT_LIFETIME_NAME]
        result = run_scipfs_command(args)
        
        self.assertEqual(result.returncode, 0, f"scipfs create failed for {self.LIB_DEFAULT_LIFETIME_NAME}. STDERR: {result.stderr}")
        self.assertIn(f"Successfully created library '{self.LIB_DEFAULT_LIFETIME_NAME}'", result.stdout)
        # Check the specific log line from library.py (verbose output goes to stderr)
        expected_log_line = f"IPNS Record Lifetime: {self.DEFAULT_LIFETIME_VAL}" 
        self.assertIn(expected_log_line, result.stderr, f"Default lifetime '{self.DEFAULT_LIFETIME_VAL}' not found in create command's STDERR. STDERR: {result.stderr}")
        
        manifest_path = self.CONFIG_DIR / f"{self.LIB_DEFAULT_LIFETIME_NAME}_manifest.json"
        self.assertTrue(manifest_path.exists(), f"Manifest file was not created: {manifest_path}")
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)
        self.assertEqual(manifest_data.get("ipns_record_lifetime"), self.DEFAULT_LIFETIME_VAL)

    def test_02_create_library_custom_lifetime(self):
        print(f"\n--- Test: Create Library with Custom Lifetime ({self.LIB_CUSTOM_LIFETIME_NAME}, {self.CUSTOM_LIFETIME_VAL}) ---")
        args = ["--verbose", "create", self.LIB_CUSTOM_LIFETIME_NAME, "--ipns-lifetime", self.CUSTOM_LIFETIME_VAL]
        result = run_scipfs_command(args, timeout=90) # Increased timeout

        self.assertEqual(result.returncode, 0, f"scipfs create failed for {self.LIB_CUSTOM_LIFETIME_NAME}. STDERR: {result.stderr}")
        self.assertIn(f"Successfully created library '{self.LIB_CUSTOM_LIFETIME_NAME}'", result.stdout)
        expected_log_line = f"IPNS Record Lifetime: {self.CUSTOM_LIFETIME_VAL}"
        self.assertIn(expected_log_line, result.stderr, f"Custom lifetime '{self.CUSTOM_LIFETIME_VAL}' not found in create command's STDERR. STDERR: {result.stderr}")

        manifest_path = self.CONFIG_DIR / f"{self.LIB_CUSTOM_LIFETIME_NAME}_manifest.json"
        self.assertTrue(manifest_path.exists(), f"Manifest file was not created: {manifest_path}")
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)
        self.assertEqual(manifest_data.get("ipns_record_lifetime"), self.CUSTOM_LIFETIME_VAL)

    def test_03_add_file_reuses_custom_lifetime(self):
        print(f"\n--- Test: Add File Reuses Custom Lifetime ({self.LIB_CUSTOM_LIFETIME_NAME}) ---")
        dummy_file_name = "test_custom_add.txt"
        dummy_file_path = Path(dummy_file_name)
        with open(dummy_file_path, "w") as f:
            f.write("Test content for custom lifetime add.")
        
        # Ensure file is deleted after test, even if test fails
        if dummy_file_path.exists(): self.addCleanup(dummy_file_path.unlink)


        args = ["--verbose", "add", self.LIB_CUSTOM_LIFETIME_NAME, str(dummy_file_path)]
        result = run_scipfs_command(args, timeout=90) # Add can take longer due to IPFS ops

        self.assertEqual(result.returncode, 0, f"scipfs add failed for {self.LIB_CUSTOM_LIFETIME_NAME}. STDERR: {result.stderr}")
        
        # Check for the specific INFO log from library.py that includes the lifetime
        # Format: INFO:scipfs.library:Published manifest CID Qm... to IPNS for key lib_name (... Lifetime: 48h)
        expected_info_log_pattern = rf"Published manifest CID [\w\d]+ to IPNS for key {self.LIB_CUSTOM_LIFETIME_NAME}.*Lifetime: {self.CUSTOM_LIFETIME_VAL}" # Removed single quotes around lib name
        
        self.assertTrue(
            re.search(expected_info_log_pattern, result.stderr), # Check stderr
            f"Custom lifetime '{self.CUSTOM_LIFETIME_VAL}' not found in 'add' command's IPNS publish log (STDERR).\nSTDERR:\n{result.stderr}"
        )

    def test_04_add_file_reuses_default_lifetime(self):
        print(f"\n--- Test: Add File Reuses Default Lifetime ({self.LIB_DEFAULT_LIFETIME_NAME}) ---")
        dummy_file_name = "test_default_add.txt"
        dummy_file_path = Path(dummy_file_name)
        with open(dummy_file_path, "w") as f:
            f.write("Test content for default lifetime add.")
        
        if dummy_file_path.exists(): self.addCleanup(dummy_file_path.unlink)

        args = ["--verbose", "add", self.LIB_DEFAULT_LIFETIME_NAME, str(dummy_file_path)]
        result = run_scipfs_command(args, timeout=90)

        self.assertEqual(result.returncode, 0, f"scipfs add failed for {self.LIB_DEFAULT_LIFETIME_NAME}. STDERR: {result.stderr}")
        
        # Check for the specific INFO log from library.py that includes the lifetime
        expected_info_log_pattern = rf"Published manifest CID [\w\d]+ to IPNS for key {self.LIB_DEFAULT_LIFETIME_NAME}.*Lifetime: {self.DEFAULT_LIFETIME_VAL}" # Removed single quotes around lib name
        
        self.assertTrue(
            re.search(expected_info_log_pattern, result.stderr), # Check stderr
            f"Default lifetime '{self.DEFAULT_LIFETIME_VAL}' not found in 'add' command's IPNS publish log (STDERR).\nSTDERR:\n{result.stderr}"
        )

if __name__ == "__main__":
    # This allows running the test file directly, e.g., python tests/integration/test_ipns_lifetime.py
    unittest.main(verbosity=2) 