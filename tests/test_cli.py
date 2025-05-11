import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import json

from click.testing import CliRunner

# Assuming your CLI script is in scipfs.cli and the main group is named `cli`
from scipfs import cli as scipfs_cli 
from scipfs.library import Library
from scipfs.ipfs import IPFSClient

# Default config dir for tests, can be overridden or mocked
TEST_CONFIG_DIR = Path(\"/tmp/.test_scipfs_config\")

class TestSciPFSCLI(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()
        # Ensure a clean test config directory for some tests if they interact with filesystem
        TEST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.patch_config_dir = patch(\'scipfs.cli.CONFIG_DIR\', TEST_CONFIG_DIR)
        self.mock_config_dir = self.patch_config_dir.start()

    def tearDown(self):
        self.patch_config_dir.stop()
        # Clean up test config dir if needed, or use tempfile.TemporaryDirectory
        # For simplicity, manual cleanup might be needed if files are written:
        # import shutil
        # if TEST_CONFIG_DIR.exists():
        #     shutil.rmtree(TEST_CONFIG_DIR)
        pass

    @patch(\'scipfs.cli.IPFSClient\')
    def test_init_command(self, MockIPFSClient): # MockIPFSClient not directly used but good practice
        result = self.runner.invoke(scipfs_cli.cli, [\'init\'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(f\"Initialized SciPFS configuration at {str(TEST_CONFIG_DIR)}\", result.output)
        self.assertTrue(TEST_CONFIG_DIR.exists())

    @patch(\'scipfs.cli.Library\') # Patch the Library class used by the CLI command
    @patch(\'scipfs.cli.IPFSClient\') # Patch the IPFSClient
    def test_create_library_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value
        
        # Configure the mock library instance to simulate successful creation
        mock_library_instance.name = \"testlib\"
        mock_library_instance.ipns_name = \"/ipns/k51testipnsname\"
        mock_library_instance.manifest_cid = \"QmTestManifestCID\"
        mock_library_instance.manifest_path = TEST_CONFIG_DIR / \"testlib_manifest.json\"

        # library.create() is called within the CLI command
        mock_library_instance.create.return_value = None 

        result = self.runner.invoke(scipfs_cli.cli, [\'create\', \'testlib\'])
        
        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockLibrary.assert_called_once_with(\"testlib\", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.create.assert_called_once()
        self.assertIn(\"Successfully created library \'testlib\'\", result.output)
        self.assertIn(\"IPNS Name (share this with others): /ipns/k51testipnsname\", result.output)
        self.assertIn(\"Initial Manifest CID: QmTestManifestCID\", result.output)

    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    def test_create_library_already_exists_value_error(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value
        mock_library_instance.create.side_effect = ValueError(\"Library configuration file already exists.\")

        result = self.runner.invoke(scipfs_cli.cli, [\'create\', \'existinglib\'])
        
        self.assertNotEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(\"Error: Library configuration file already exists.\", result.output)
        MockLibrary.assert_called_once_with(\"existinglib\", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.create.assert_called_once()

    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    def test_join_library_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value # This is the one used for the temp instance in join

        # Configure the mock_library_instance that join() will modify
        def mock_join_method(ipns_name_to_join):
            mock_library_instance.name = \"joinedlib\" # Name is updated from manifest
            mock_library_instance.ipns_name = ipns_name_to_join
            mock_library_instance.manifest_cid = \"QmJoinedManifestCID\"
            mock_library_instance.manifest_path = TEST_CONFIG_DIR / \"joinedlib_manifest.json\"

        mock_library_instance.join.side_effect = mock_join_method
        
        test_ipns_name = \"/ipns/k51qJoinMe\"
        result = self.runner.invoke(scipfs_cli.cli, [\'join\', test_ipns_name])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        # Library is instantiated with a placeholder name first
        MockLibrary.assert_called_once_with(\"temp_join_placeholder\", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.join.assert_called_once_with(test_ipns_name)
        self.assertIn(f\"Successfully joined library \'joinedlib\' using IPNS name: {test_ipns_name}\", result.output)
        self.assertIn(\"Manifest (CID: QmJoinedManifestCID) saved to\", result.output)

    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    def test_join_library_not_found(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value
        mock_library_instance.join.side_effect = FileNotFoundError(\"Could not resolve IPNS name\")

        test_ipns_name = \"/ipns/k51qNonExistent\"
        result = self.runner.invoke(scipfs_cli.cli, [\'join\', test_ipns_name])

        self.assertNotEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(f\"Error joining library: Could not resolve IPNS name \'{test_ipns_name}\'\", result.output)

    @patch(\'scipfs.cli.scipfs_config.get_username\', return_value=\"testuser\")
    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    @patch(\'pathlib.Path.exists\', return_value=True) # Mock file_path.exists() for the file to add
    def test_add_file_owner_success(self, MockPathExists, MockIPFSClient, MockLibrary, MockGetUsername):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = \"ownerlib\"
        mock_library_instance.manifest_path = TEST_CONFIG_DIR / \"ownerlib_manifest.json\"
        mock_library_instance.manifest_path.exists.return_value = True # Manifest for ownerlib exists
        original_cid = \"QmOriginalCID\"
        new_cid = \"QmNewCID\"
        mock_library_instance.manifest_cid = original_cid
        
        # Simulate add_file changing the manifest_cid and having IPNS info (owner)
        def mock_add_file_effect(file_path_arg, username_arg):
            mock_library_instance.manifest_cid = new_cid
            mock_library_instance.ipns_key_name = \"ownerlib\" # This instance is the owner
            mock_library_instance.ipns_name = \"/ipns/k51ownerlib\"

        mock_library_instance.add_file.side_effect = mock_add_file_effect
        
        # Create a dummy file to "add"
        dummy_file_path = Path(\"./dummy.txt\")
        with open(dummy_file_path, \"w\") as f: f.write(\"test content\")

        result = self.runner.invoke(scipfs_cli.cli, [\'add\', \'ownerlib\', str(dummy_file_path)])
        
        dummy_file_path.unlink() # Clean up dummy file

        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockGetUsername.assert_called_once()
        MockLibrary.assert_called_once_with(\"ownerlib\", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.add_file.assert_called_once_with(dummy_file_path, \"testuser\")
        self.assertIn(f\"Added \'{dummy_file_path.name}\' to library \'ownerlib\'\", result.output)
        self.assertIn(f\"New Manifest CID: {new_cid}\", result.output)
        self.assertIn(\"The library\'s IPNS record (/ipns/k51ownerlib) has been updated\", result.output)

    @patch(\'scipfs.cli.scipfs_config.get_username\', return_value=\"testuser\")
    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    @patch(\'pathlib.Path.exists\', return_value=True) 
    def test_add_file_non_owner_success(self, MockPathExists, MockIPFSClient, MockLibrary, MockGetUsername):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = \"joinedlib\"
        mock_library_instance.manifest_path = TEST_CONFIG_DIR / \"joinedlib_manifest.json\"
        mock_library_instance.manifest_path.exists.return_value = True
        original_cid = \"QmOriginalJoinedCID\"
        new_cid = \"QmNewJoinedCID\"
        mock_library_instance.manifest_cid = original_cid
        
        def mock_add_file_effect(file_path_arg, username_arg):
            mock_library_instance.manifest_cid = new_cid
            mock_library_instance.ipns_key_name = None # This instance is NOT the owner
            mock_library_instance.ipns_name = \"/ipns/k51someotherlib\" # It knows the IPNS name it joined

        mock_library_instance.add_file.side_effect = mock_add_file_effect
        
        dummy_file_path = Path(\"./dummy_non_owner.txt\")
        with open(dummy_file_path, \"w\") as f: f.write(\"test content\")

        result = self.runner.invoke(scipfs_cli.cli, [\'add\', \'joinedlib\', str(dummy_file_path)])
        
        dummy_file_path.unlink()

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(f\"New Manifest CID: {new_cid}\", result.output)
        self.assertIn(\"Your local manifest is updated. If this is a shared library you don\'t own,\", result.output)
        self.assertNotIn(\"The library\'s IPNS record has been updated\", result.output)


    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    def test_info_library_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = \"infolib\"
        mock_library_instance.manifest_path = TEST_CONFIG_DIR / \"infolib_manifest.json\"
        mock_library_instance.manifest_path.exists.return_value = True
        mock_library_instance.ipns_name = \"/ipns/k51infolib\"
        mock_library_instance.ipns_key_name = \"infolib\" # Owner
        mock_library_instance.manifest_cid = \"QmInfoCID\"
        mock_library_instance.manifest = {\"files\": {\"file1.txt\": {}, \"file2.pdf\": {}}}

        result = self.runner.invoke(scipfs_cli.cli, [\'info\', \'infolib\'])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockLibrary.assert_called_once_with(\"infolib\", TEST_CONFIG_DIR, mock_ipfs_instance)
        self.assertIn(\"Information for library: infolib\", result.output)
        self.assertIn(\"IPNS Name: /ipns/k51infolib\", result.output)
        self.assertIn(\"IPNS Key Name (local): infolib\", result.output)
        self.assertIn(\"Current Manifest CID: QmInfoCID\", result.output)
        self.assertIn(\"Number of files: 2\", result.output)
    
    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    def test_update_library_no_change(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        
        # This mock is for the initial load of the library to be updated
        initial_lib_mock = MagicMock(spec=Library)
        initial_lib_mock.name = \"updatelib\"
        initial_lib_mock.manifest_path = TEST_CONFIG_DIR / \"updatelib_manifest.json\"
        initial_lib_mock.manifest_path.exists.return_value = True
        initial_lib_mock.ipns_name = \"/ipns/k51updatelib\"
        initial_lib_mock.manifest_cid = \"QmSameCID\"

        # This mock is for the \'update_fetcher\' instance
        fetcher_lib_mock = MagicMock(spec=Library)
        
        # join() on fetcher_lib_mock will set its attributes
        def join_effect_for_fetcher(ipns_name):
            fetcher_lib_mock.name = \"updatelib\"
            fetcher_lib_mock.manifest_cid = \"QmSameCID\" # IPNS resolves to the same CID
            fetcher_lib_mock.manifest_path = TEST_CONFIG_DIR / \"updatelib_manifest.json\"
        fetcher_lib_mock.join.side_effect = join_effect_for_fetcher
        
        # MockLibrary will be called twice: once for initial load, once for fetcher
        MockLibrary.side_effect = [initial_lib_mock, fetcher_lib_mock]

        result = self.runner.invoke(scipfs_cli.cli, [\'update\', \'updatelib\'])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        initial_lib_mock.manifest_path.exists.assert_called_once()
        self.assertTrue(initial_lib_mock.ipns_name) # Check ipns_name was accessed
        
        # Check calls to Library constructor
        self.assertEqual(MockLibrary.call_count, 2)
        MockLibrary.assert_any_call(\"updatelib\", TEST_CONFIG_DIR, mock_ipfs_instance)
        MockLibrary.assert_any_call(\"temp_update_updatelib\", TEST_CONFIG_DIR, mock_ipfs_instance)
        
        fetcher_lib_mock.join.assert_called_once_with(\"/ipns/k51updatelib\")
        self.assertIn(\"Library \'updatelib\' is already up-to-date.\", result.output)
        self.assertIn(\"Local CID: QmSameCID\", result.output)

    @patch(\'scipfs.cli.Library\')
    @patch(\'scipfs.cli.IPFSClient\')
    def test_update_library_with_changes(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        
        initial_lib_mock = MagicMock(spec=Library)
        initial_lib_mock.name = \"updatelib2\"
        initial_lib_mock.manifest_path = TEST_CONFIG_DIR / \"updatelib2_manifest.json\"
        initial_lib_mock.manifest_path.exists.return_value = True
        initial_lib_mock.ipns_name = \"/ipns/k51updatelib2\"
        initial_lib_mock.manifest_cid = \"QmOldCID\" # Current local CID

        fetcher_lib_mock = MagicMock(spec=Library)
        def join_effect_for_fetcher(ipns_name):
            fetcher_lib_mock.name = \"updatelib2\"
            fetcher_lib_mock.manifest_cid = \"QmNewCIDFromIPNS\" # IPNS resolves to a new CID
            fetcher_lib_mock.manifest_path = TEST_CONFIG_DIR / \"updatelib2_manifest.json\"
        fetcher_lib_mock.join.side_effect = join_effect_for_fetcher
        
        MockLibrary.side_effect = [initial_lib_mock, fetcher_lib_mock]

        result = self.runner.invoke(scipfs_cli.cli, [\'update\', \'updatelib2\'])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(\"Library \'updatelib2\' updated.\", result.output)
        self.assertIn(\"Old Manifest CID: QmOldCID\", result.output)
        self.assertIn(\"New Manifest CID: QmNewCIDFromIPNS\", result.output)

if __name__ == \'__main__\':
    unittest.main() 