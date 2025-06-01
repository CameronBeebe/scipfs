import unittest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import json
from datetime import datetime

# Ensure scipfs modules are importable. Adjust path if tests are run from a different root.
# This might require adding the project root to sys.path or using `python -m unittest discover`
try:
    from scipfs.library import Library
    from scipfs.ipfs import IPFSClient, SciPFSException, SciPFSFileNotFoundError
except ImportError:
    # Fallback for cases where tests might be run in a way that scipfs is not directly in pythonpath
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scipfs.library import Library
    from scipfs.ipfs import IPFSClient, SciPFSException, SciPFSFileNotFoundError


class TestLibrary(unittest.TestCase):

    def setUp(self):
        self.mock_ipfs_client = MagicMock(spec=IPFSClient)
        self.config_dir = Path("/tmp/scipfs_test_config")
        self.config_dir.mkdir(parents=True, exist_ok=True) # Ensure config_dir exists for manifest path
        
        self.library_name = "testlib"
        # Reset manifest file if it exists from a previous run
        self.manifest_file_path = self.config_dir / f"{self.library_name}_manifest.json"
        if self.manifest_file_path.exists():
            self.manifest_file_path.unlink()

    def tearDown(self):
        # Clean up manifest files created during tests
        for f_path in self.config_dir.glob("*.json"):
            f_path.unlink()
        if self.config_dir.exists() and not list(self.config_dir.iterdir()): # only remove if empty
            self.config_dir.rmdir()


    def test_create_library_and_save_manifest_no_internal_cid(self):
        # Mock IPFS client methods used by create and _save_manifest
        self.mock_ipfs_client.generate_ipns_key.return_value = {"Name": self.library_name, "Id": "k_test_peer_id"}
        self.mock_ipfs_client.add_json.return_value = "QmManifestCID1"
        
        library = Library(self.library_name, self.config_dir, self.mock_ipfs_client)
        library.create()

        self.assertEqual(library.manifest_cid, "QmManifestCID1")
        self.assertTrue(self.manifest_file_path.exists())

        with open(self.manifest_file_path, "r") as f:
            saved_manifest_data = json.load(f)
        
        self.assertNotIn("latest_manifest_cid", saved_manifest_data, "latest_manifest_cid should not be in saved manifest")
        self.assertEqual(saved_manifest_data.get("name"), self.library_name)
        self.assertEqual(saved_manifest_data.get("ipns_key_name"), self.library_name)
        self.assertEqual(saved_manifest_data.get("ipns_name"), "/ipns/k_test_peer_id")
        self.mock_ipfs_client.pin.assert_called_with("QmManifestCID1")
        self.mock_ipfs_client.publish_to_ipns.assert_called_with(self.library_name, "QmManifestCID1", lifetime="24h")

    def test_add_file_iso_timestamp(self):
        library = Library(self.library_name, self.config_dir, self.mock_ipfs_client)
        # Initial save to create manifest structure on disk if needed by add_file's _save_manifest
        self.mock_ipfs_client.add_json.return_value = "QmInitialManifest"
        library._save_manifest() 

        mock_file_path = Path("dummy_file.txt")
        
        # Mock file operations and IPFS calls for add_file
        with patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as mock_stat:
            
            mock_stat.return_value.st_size = 100
            # Use a fixed timestamp for predictable ISO string
            fixed_timestamp = datetime(2023, 1, 1, 12, 0, 0).timestamp()
            mock_stat.return_value.st_mtime = fixed_timestamp

            self.mock_ipfs_client.add_file.return_value = "QmFileCID1"
            self.mock_ipfs_client.add_json.return_value = "QmManifestCIDAfterAdd" # For the _save_manifest call

            library.add_file(mock_file_path, "testuser")

        self.assertIn(mock_file_path.name, library.manifest["files"])
        file_info = library.manifest["files"][mock_file_path.name]
        
        expected_iso_ts = datetime.fromtimestamp(fixed_timestamp).isoformat()
        self.assertEqual(file_info["added_timestamp"], expected_iso_ts)
        self.assertEqual(file_info["added_by"], "testuser")
        self.assertEqual(file_info["cid"], "QmFileCID1")
        self.mock_ipfs_client.add_file.assert_called_with(mock_file_path)
        self.mock_ipfs_client.pin.assert_any_call("QmFileCID1") # Pinning file CID
        self.mock_ipfs_client.pin.assert_any_call("QmManifestCIDAfterAdd") # Pinning new manifest CID


    @patch('scipfs.library.Library._save_manifest') # Mock _save_manifest to isolate update logic
    def test_update_from_ipns_success_update(self, mock_save_manifest):
        initial_manifest_cid = "QmOldManifestCID"
        new_resolved_cid = "QmNewManifestCID"
        
        # Setup library with an initial state
        library = Library(self.library_name, self.config_dir, self.mock_ipfs_client)
        library.ipns_name = "/ipns/k_test_peer_id"
        library.manifest_cid = initial_manifest_cid
        library.manifest = {"name": self.library_name, "files": {"old_file.txt": {"cid": "QmOldFile"}}, "ipns_name": library.ipns_name}

        # Mock IPFS client methods used by update_from_ipns
        self.mock_ipfs_client.resolve_ipns_name.return_value = f"/ipfs/{new_resolved_cid}"
        new_manifest_content = {"name": self.library_name, "files": {"new_file.txt": {"cid": "QmNewFile"}}, "ipns_name": library.ipns_name}
        self.mock_ipfs_client.get_json.return_value = new_manifest_content

        updated = library.update_from_ipns()

        self.assertTrue(updated)
        self.mock_ipfs_client.resolve_ipns_name.assert_called_with(library.ipns_name)
        self.mock_ipfs_client.get_json.assert_called_with(new_resolved_cid)
        self.assertEqual(library.manifest_cid, new_resolved_cid)
        self.assertEqual(library.manifest, new_manifest_content)
        mock_save_manifest.assert_called_once() # Check that it attempts to save the new state

    @patch('scipfs.library.Library._save_manifest')
    def test_update_from_ipns_no_update_needed(self, mock_save_manifest):
        current_manifest_cid = "QmCurrentManifestCID"
        library = Library(self.library_name, self.config_dir, self.mock_ipfs_client)
        library.ipns_name = "/ipns/k_test_peer_id"
        library.manifest_cid = current_manifest_cid
        library.manifest = {"name": self.library_name, "files": {}, "ipns_name": library.ipns_name}

        self.mock_ipfs_client.resolve_ipns_name.return_value = f"/ipfs/{current_manifest_cid}"

        updated = library.update_from_ipns()

        self.assertFalse(updated)
        self.mock_ipfs_client.resolve_ipns_name.assert_called_with(library.ipns_name)
        self.mock_ipfs_client.get_json.assert_not_called()
        mock_save_manifest.assert_not_called()

    def test_update_from_ipns_no_ipns_name_set(self):
        library = Library(self.library_name, self.config_dir, self.mock_ipfs_client)
        # library.ipns_name is not set
        with self.assertRaisesRegex(ValueError, "Library does not have an IPNS name for updates."):
            library.update_from_ipns()

    def test_update_from_ipns_resolve_fails(self):
        library = Library(self.library_name, self.config_dir, self.mock_ipfs_client)
        library.ipns_name = "/ipns/k_test_peer_id"
        self.mock_ipfs_client.resolve_ipns_name.side_effect = SciPFSFileNotFoundError("Could not resolve")

        with self.assertRaises(SciPFSFileNotFoundError):
            library.update_from_ipns()
            
    def test_get_file_info(self):
        library = Library(self.library_name, self.config_dir, self.mock_ipfs_client)
        file_data = {"cid": "QmFile1", "size": 123, "added_timestamp": datetime.now().isoformat(), "added_by": "user1"}
        library.manifest["files"]["test_file.txt"] = file_data

        info = library.get_file_info("test_file.txt")
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "test_file.txt")
        self.assertEqual(info["cid"], "QmFile1")
        self.assertEqual(info["added_by"], "user1")

        info_none = library.get_file_info("non_existent_file.txt")
        self.assertIsNone(info_none)

if __name__ == '__main__':
    unittest.main() 