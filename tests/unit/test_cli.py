import unittest
from unittest.mock import patch, MagicMock, mock_open, ANY
from pathlib import Path
import json
import sys

from click.testing import CliRunner

from scipfs.cli import cli, MinimalIPFSClient
from scipfs.ipfs import IPFSClient, IPFSConnectionError, KuboVersionError, SciPFSGoWrapperError
from scipfs.library import Library
from scipfs.config import SciPFSConfig

# Default config dir for tests
TEST_CONFIG_DIR = Path("/tmp/.test_scipfs_config")

class TestSciPFSCLI(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        # Set up config mocking
        self.mock_config_patcher = patch('scipfs.cli.scipfs_config_instance')
        self.mock_config_instance = self.mock_config_patcher.start()
        self.mock_config_instance.get_username.return_value = "testuser"
        self.mock_config_instance.get_api_addr_for_client.return_value = "/ip4/127.0.0.1/tcp/5001"
        self.mock_config_instance.config_file_path = Path("/tmp/fake_config.json")
        
        # Set up config dir patching
        self.patch_config_dir = patch('scipfs.cli.CONFIG_DIR', TEST_CONFIG_DIR)
        self.mock_config_dir = self.patch_config_dir.start()
        
        # Common API address
        self.api_addr = "/ip4/127.0.0.1/tcp/5001"

    def tearDown(self):
        self.mock_config_patcher.stop()
        self.patch_config_dir.stop()

    @patch('scipfs.cli.IPFSClient')
    def test_cli_group_ipfs_client_init_success(self, MockIPFSClient):
        mock_client_instance = MockIPFSClient.return_value
        mock_client_instance.check_ipfs_daemon.return_value = None
        
        with patch('scipfs.cli.Library') as MockLibrary:
            mock_lib_instance = MockLibrary.return_value
            mock_lib_instance.create.return_value = None
            mock_lib_instance.ipns_name = "/ipns/testipnsname"
            mock_lib_instance.manifest_cid = "QmTestManifest"
            
            result = self.runner.invoke(cli, ['create', 'mylib'])
        
        MockIPFSClient.assert_called_once()
        mock_client_instance.check_ipfs_daemon.assert_called_once()
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Successfully created library 'mylib'", result.output)

    @patch('scipfs.cli.IPFSClient')
    def test_cli_group_ipfs_client_init_connection_error(self, MockIPFSClient):
        MockIPFSClient.return_value.check_ipfs_daemon.side_effect = IPFSConnectionError("Daemon down")
        
        result = self.runner.invoke(cli, ['create', 'mylib'])
        self.assertNotEqual(result.exit_code, 0, msg="Command should fail if IPFS connect fails")
        self.assertIn("Error: Could not connect to IPFS API.", result.output)
        self.assertIn("Daemon down", result.output)

    @patch('scipfs.cli.IPFSClient')
    def test_cli_group_ipfs_client_init_version_error(self, MockIPFSClient):
        MockIPFSClient.return_value.check_ipfs_daemon.side_effect = KuboVersionError("Wrong version")

        result = self.runner.invoke(cli, ['pin', 'cid', 'QmABC'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error: IPFS version mismatch.", result.output)
        self.assertIn("Wrong version", result.output)

    def test_init_command(self):
        with patch('scipfs.cli.CONFIG_DIR') as mock_cfg_dir, \
             patch.object(SciPFSConfig, '_save_config') as mock_save_cfg:
            
            mock_cfg_dir.mkdir.return_value = None
            mock_config_path = MagicMock(spec=Path)
            mock_config_path.exists.return_value = False
            self.mock_config_instance.config_file_path = mock_config_path

            result = self.runner.invoke(cli, ['init'])

            self.assertEqual(result.exit_code, 0, result.output)
            mock_cfg_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
            self.mock_config_instance._save_config.assert_called_once()
            self.assertIn("Initialized SciPFS configuration", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_create_library_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value
        
        mock_library_instance.name = "testlib"
        mock_library_instance.ipns_name = "/ipns/k51testipnsname"
        mock_library_instance.manifest_cid = "QmTestManifestCID"
        mock_library_instance.manifest_path = TEST_CONFIG_DIR / "testlib_manifest.json"
        mock_library_instance.create.return_value = None

        result = self.runner.invoke(cli, ['create', 'testlib'])
        
        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockLibrary.assert_called_once_with("testlib", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.create.assert_called_once()
        self.assertIn("Successfully created library 'testlib'", result.output)
        self.assertIn("IPNS Name (share this with others): /ipns/k51testipnsname", result.output)
        self.assertIn("Initial Manifest CID: QmTestManifestCID", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_create_library_already_exists_error(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value
        mock_library_instance.create.side_effect = ValueError("Library configuration file already exists.")

        result = self.runner.invoke(cli, ['create', 'existinglib'])
        
        self.assertNotEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Error: Library configuration file already exists.", result.output)
        MockLibrary.assert_called_once_with("existinglib", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.create.assert_called_once()

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_join_library_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        def mock_join_method(ipns_name_to_join):
            mock_library_instance.name = "joinedlib"
            mock_library_instance.ipns_name = ipns_name_to_join
            mock_library_instance.manifest_cid = "QmJoinedManifestCID"
            mock_library_instance.manifest_path = TEST_CONFIG_DIR / "joinedlib_manifest.json"

        mock_library_instance.join.side_effect = mock_join_method
        
        test_ipns_name = "/ipns/k51JoinMe"
        result = self.runner.invoke(cli, ['join', test_ipns_name])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockLibrary.assert_called_once_with("temp_join_placeholder", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.join.assert_called_once_with(test_ipns_name)
        self.assertIn(f"Successfully joined library 'joinedlib' using IPNS name: {test_ipns_name}", result.output)
        self.assertIn("Manifest (CID: QmJoinedManifestCID) saved to", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_join_library_not_found(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value
        mock_library_instance.join.side_effect = FileNotFoundError("Could not resolve IPNS name")

        test_ipns_name = "/ipns/k51qNonExistent"
        result = self.runner.invoke(cli, ['join', test_ipns_name])

        self.assertNotEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(f"Error joining library: Could not resolve IPNS name '{test_ipns_name}'", result.output)

    @patch('scipfs.cli.scipfs_config_instance.get_username', return_value="testuser")
    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    @patch('pathlib.Path.exists', return_value=True)
    def test_add_file_owner_success(self, MockPathExists, MockIPFSClient, MockLibrary, MockGetUsername):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = "ownerlib"
        mock_library_instance.manifest_path = TEST_CONFIG_DIR / "ownerlib_manifest.json"
        mock_library_instance.manifest_path.exists.return_value = True
        original_cid = "QmOriginalCID"
        new_cid = "QmNewCID"
        mock_library_instance.manifest_cid = original_cid
        
        def mock_add_file_effect(file_path_arg, username_arg):
            mock_library_instance.manifest_cid = new_cid
            mock_library_instance.ipns_key_name = "ownerlib"
            mock_library_instance.ipns_name = "/ipns/k51ownerlib"

        mock_library_instance.add_file.side_effect = mock_add_file_effect
        
        dummy_file_path = Path("./dummy.txt")
        with open(dummy_file_path, "w") as f:
            f.write("test content")

        result = self.runner.invoke(cli, ['add', 'ownerlib', str(dummy_file_path)])
        
        dummy_file_path.unlink()

        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockGetUsername.assert_called_once()
        MockLibrary.assert_called_once_with("ownerlib", TEST_CONFIG_DIR, mock_ipfs_instance)
        mock_library_instance.add_file.assert_called_once_with(dummy_file_path, "testuser")
        self.assertIn(f"Added '{dummy_file_path.name}' to library 'ownerlib'", result.output)
        self.assertIn(f"New Manifest CID: {new_cid}", result.output)
        self.assertIn("The library's IPNS record (/ipns/k51ownerlib) has been updated", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_update_command_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_client_ctx = MockIPFSClient.return_value
        mock_ipfs_client_ctx.check_ipfs_daemon.return_value = None
        
        mock_library_instance = MockLibrary.return_value
        mock_library_instance.update_from_ipns.return_value = True
        mock_library_instance.manifest_cid = "QmNewManifest"
        mock_library_instance.name = "updatedlib"
        mock_library_instance.manifest = {"ipns_name": "/ipns/xyz", "files": {}}
        mock_library_instance.manifest_path.exists.return_value = True

        result = self.runner.invoke(cli, ['--verbose', 'update', 'updatedlib'], obj={'IPFS_CLIENT': mock_ipfs_client_ctx})

        self.assertEqual(result.exit_code, 0, result.output)
        MockLibrary.assert_called_with('updatedlib', ANY, mock_ipfs_client_ctx)
        mock_library_instance.update_from_ipns.assert_called_once()
        self.assertIn("Library 'updatedlib' is already up-to-date", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_list_pinned_matched(self, MockIPFSClient, MockLibrary):
        mock_ipfs_client_ctx = MockIPFSClient.return_value
        mock_ipfs_client_ctx.check_ipfs_daemon.return_value = None
        mock_ipfs_client_ctx.list_pinned_cids.return_value = {
            "QmManifest1": {"Type": "recursive"},
            "QmFile1InLib1": {"Type": "recursive"},
            "QmOtherPin": {"Type": "direct"}
        }

        mock_lib_instance = MockLibrary.return_value
        mock_lib_instance.name = "lib1"
        mock_lib_instance.manifest_cid = "QmManifest1"
        mock_lib_instance.list_files.return_value = [
            {"name": "file1.txt", "cid": "QmFile1InLib1"}
        ]
        mock_lib_instance.manifest_path.exists.return_value = True
        mock_lib_instance.manifest = {"ipns_name": "/ipns/k51lib1", "files": {"file1.txt": {"cid": "QmFile1InLib1"}}}

        with patch('scipfs.cli.CONFIG_DIR') as mock_config_dir:
            mock_manifest_file = MagicMock(spec=Path)
            mock_manifest_file.name = "lib1_manifest.json"
            mock_manifest_file.stem = "lib1"
            mock_config_dir.glob.return_value = [mock_manifest_file]
            
            result = self.runner.invoke(cli, ['list-pinned'], obj={'IPFS_CLIENT': mock_ipfs_client_ctx})

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Fetching pinned CIDs from local IPFS node", result.output)
        self.assertIn("Found 3 pinned CIDs", result.output)
        self.assertIn("Matching pinned CIDs to local SciPFS libraries", result.output)
        self.assertIn("Library: lib1", result.output)
        self.assertIn("Manifest: QmManifest1", result.output)
        self.assertIn("Name: file1.txt, CID: QmFile1InLib1", result.output)
        self.assertIn("Other pinned CIDs", result.output)
        self.assertIn("QmOtherPin", result.output)
        MockLibrary.assert_any_call("lib1", mock_config_dir, ANY)

    @patch('scipfs.cli.IPFSClient')
    def test_doctor_command_all_ok(self, MockIPFSClient):
        mock_client_instance = MockIPFSClient.return_value
        mock_client_instance.check_ipfs_daemon.return_value = None
        mock_client_instance.get_version_str.return_value = "0.25.0"
        mock_client_instance.api_addr = self.api_addr
        mock_client_instance.check_version.return_value = True
        mock_client_instance.go_wrapper_path = "/fake/scipfs_go_helper"

        self.mock_config_instance.get_username.return_value = "testuser"
        mock_config_path = MagicMock(spec=Path)
        mock_config_path.exists.return_value = True
        self.mock_config_instance.config_file_path = mock_config_path
        self.mock_config_instance._read_config.return_value = {}

        with patch('pathlib.Path.exists') as mock_path_exists, \
             patch('os.access') as mock_os_access:
            mock_path_exists.side_effect = [True, True, True, True]
            mock_os_access.return_value = True

            result = self.runner.invoke(cli, ['doctor'], obj={'IPFS_CLIENT': mock_client_instance})
        
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("[OK] Configuration directory exists", result.output)
        self.assertIn("[OK] Main config file exists", result.output)
        self.assertIn("[INFO] Username configured: testuser", result.output)
        self.assertIn("[OK] IPFS daemon connected successfully", result.output)
        self.assertIn("[INFO] Connected IPFS daemon version: 0.25.0", result.output)
        self.assertIn("[INFO] SciPFS requires Kubo: 0.23.0", result.output)
        self.assertIn("[SUCCESS] All checks passed", result.output)

    def test_config_show_command(self):
        self.mock_config_instance.get_username.return_value = "janedoe"
        self.mock_config_instance.get_api_addr_for_client.return_value = "/ip4/1.2.3.4/tcp/5002"
        
        result = self.runner.invoke(cli, ['config', 'show'])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Username: janedoe", result.output)
        self.assertIn("IPFS API Address: /ip4/1.2.3.4/tcp/5002", result.output)
        self.assertIn(str(self.mock_config_instance.config_file_path), result.output)

    @patch('scipfs.cli.scipfs_config_instance.get_username', return_value="testuser")
    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    @patch('pathlib.Path.exists', return_value=True)
    def test_add_file_non_owner_success(self, MockPathExists, MockIPFSClient, MockLibrary, MockGetUsername):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = "joinedlib"
        mock_library_instance.manifest_path = TEST_CONFIG_DIR / "joinedlib_manifest.json"
        mock_library_instance.manifest_path.exists.return_value = True
        original_cid = "QmOriginalJoinedCID"
        new_cid = "QmNewJoinedCID"
        mock_library_instance.manifest_cid = original_cid
        
        def mock_add_file_effect(file_path_arg, username_arg):
            mock_library_instance.manifest_cid = new_cid
            mock_library_instance.ipns_key_name = None # This instance is NOT the owner
            mock_library_instance.ipns_name = "/ipns/k51someotherlib"

        mock_library_instance.add_file.side_effect = mock_add_file_effect
        
        dummy_file_path = Path("./dummy_non_owner.txt")
        with open(dummy_file_path, "w") as f:
            f.write("test content")

        result = self.runner.invoke(cli, ['add', 'joinedlib', str(dummy_file_path)])
        
        dummy_file_path.unlink()

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(f"New Manifest CID: {new_cid}", result.output)
        self.assertIn("Your local manifest is updated. If this is a shared library you don't own,", result.output)
        self.assertNotIn("The library's IPNS record has been updated", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_info_library_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = "infolib"
        mock_library_instance.manifest_path.exists.return_value = True
        mock_library_instance.manifest_path.__str__.return_value = str(TEST_CONFIG_DIR / "infolib_manifest.json")
        mock_library_instance.manifest_path.name = (TEST_CONFIG_DIR / "infolib_manifest.json").name

        mock_library_instance.ipns_name = "/ipns/k51infolib"
        mock_library_instance.ipns_key_name = "infolib"
        mock_library_instance.manifest_cid = "QmInfoCID"
        mock_library_instance.manifest = {
            "ipns_name": "/ipns/k51infolib",
            "owner": "testuser",
            "description": "Test library",
            "files": {"file1.txt": {}, "file2.pdf": {}},
            "last_modified": "2024-03-21T12:00:00Z"
        }
        mock_library_instance.manifest_data = mock_library_instance.manifest
        mock_library_instance._load_manifest = lambda: None

        result = self.runner.invoke(cli, ['info', 'infolib'])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockLibrary.assert_called_once_with("infolib", TEST_CONFIG_DIR, ANY)
        self.assertIn("Information for library: infolib", result.output)
        self.assertIn("IPNS Name (if published): /ipns/k51infolib", result.output)
        self.assertIn("Owner/Creator: testuser", result.output)
        self.assertIn("Description: Test library", result.output)
        self.assertIn("Number of files: 2", result.output)
        self.assertIn("Last Modified (Manifest): 2024-03-21T12:00:00Z", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_update_library_with_changes(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_ipfs_instance.check_ipfs_daemon.return_value = None

        # Create and configure the initial library mock
        initial_lib_mock = MagicMock(spec=Library)
        initial_lib_mock.name = "updatelib2"
        initial_lib_mock.manifest_path = MagicMock(spec=Path)
        initial_lib_mock.manifest_path.exists.return_value = True
        initial_lib_mock.manifest_path.__str__.return_value = str(TEST_CONFIG_DIR / "updatelib2_manifest.json")
        initial_lib_mock.manifest_path.name = (TEST_CONFIG_DIR / "updatelib2_manifest.json").name

        initial_lib_mock.ipns_name = "/ipns/k51updatelib2"
        initial_lib_mock.manifest_cid = "QmOldCID"
        initial_manifest = {"ipns_name": "/ipns/k51updatelib2", "files": {}}
        initial_lib_mock.manifest = initial_manifest
        initial_lib_mock.manifest_data = initial_manifest.copy()

        # Create and configure the fetcher library mock
        fetcher_lib_mock = MagicMock(spec=Library)
        fetcher_lib_mock.name = "updatelib2"
        fetcher_lib_mock.manifest_cid = "QmNewCIDFromIPNS"
        fetcher_lib_mock.manifest_path = TEST_CONFIG_DIR / "updatelib2_manifest.json"
        new_manifest = {"ipns_name": "/ipns/k51updatelib2", "files": {"newfile.txt": {}}}
        fetcher_lib_mock.manifest = new_manifest
        fetcher_lib_mock.manifest_data = new_manifest.copy()

        def join_effect_for_fetcher(ipns_name):
            return True
        fetcher_lib_mock.join.side_effect = join_effect_for_fetcher

        def update_from_ipns_effect():
            initial_lib_mock.manifest_cid = fetcher_lib_mock.manifest_cid
            initial_lib_mock.manifest = fetcher_lib_mock.manifest.copy()
            initial_lib_mock.manifest_data = fetcher_lib_mock.manifest_data.copy()
            return True
        initial_lib_mock.update_from_ipns = update_from_ipns_effect

        MockLibrary.side_effect = [initial_lib_mock, fetcher_lib_mock]

        result = self.runner.invoke(cli, ['update', 'updatelib2'])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Updating library 'updatelib2' from IPNS name: /ipns/k51updatelib2", result.output)
        self.assertIn("New Manifest CID: QmNewCIDFromIPNS", result.output)
        self.assertEqual(initial_lib_mock.manifest, new_manifest)
        self.assertEqual(initial_lib_mock.manifest_data, new_manifest)

    @patch('scipfs.cli.scipfs_config_instance.set_username')
    def test_config_set_username_success(self, mock_set_username):
        result = self.runner.invoke(cli, ['config', 'set', 'username', 'newuser'])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_set_username.assert_called_once_with('newuser')
        self.assertIn("Username set to: newuser", result.output)

    @patch('scipfs.cli.scipfs_config_instance.set_username')
    def test_config_set_username_too_short(self, mock_set_username):
        def side_effect_for_set_username(username_val):
            if len(username_val) < 3:
                raise ValueError("Username must be at least 3 characters long.")
        mock_set_username.side_effect = side_effect_for_set_username
        
        result = self.runner.invoke(cli, ['config', 'set', 'username', 'nu'])
        self.assertNotEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Error: Username must be at least 3 characters long.", result.output)

    @patch('scipfs.cli.IPFSClient')
    def test_pin_cid_success(self, MockIPFSClient):
        mock_ipfs_instance = MockIPFSClient.return_value
        test_cid = "QmTestCIDForPinning"

        result = self.runner.invoke(cli, ['pin', 'cid', test_cid])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_ipfs_instance.pin.assert_called_once_with(test_cid)
        self.assertIn(f"Attempting to pin CID: {test_cid}", result.output)
        self.assertIn(f"Successfully pinned CID: {test_cid}", result.output)

    def test_pin_cid_invalid_format(self):
        result = self.runner.invoke(cli, ['pin', 'cid', 'invalidcidformat'])
        self.assertNotEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("invalid cid: selected encoding not supported", result.output)

    @patch('scipfs.cli.IPFSClient')
    def test_pin_cid_ipfs_connection_error(self, MockIPFSClient):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_ipfs_instance.pin.side_effect = ConnectionError("Failed to connect to IPFS daemon")
        test_cid = "QmValidCID"

        result = self.runner.invoke(cli, ['pin', 'cid', test_cid])

        self.assertNotEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Error pinning CID QmValidCID: Failed to connect to IPFS daemon", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_pin_library_success(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = "pinlib"
        mock_library_instance.manifest_path.exists.return_value = True
        mock_library_instance.manifest_cid = "QmPinManifestCID"
        mock_files = [
            {'name': 'file1.txt', 'cid': 'QmFile1CID'},
            {'name': 'file2.pdf', 'cid': 'QmFile2CID'}
        ]
        mock_library_instance.list_files.return_value = mock_files

        result = self.runner.invoke(cli, ['pin', 'library', 'pinlib'])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        MockLibrary.assert_called_once_with("pinlib", TEST_CONFIG_DIR, mock_ipfs_instance)
        self.assertIn("Pinning library 'pinlib'", result.output)
        self.assertIn("Pinning manifest (CID: QmPinManifestCID)", result.output)
        self.assertIn("Manifest pinned successfully", result.output)
        self.assertIn("Pinning 2 file(s) in library 'pinlib'", result.output)
        self.assertIn("Finished pinning files: 2 succeeded, 0 failed/skipped", result.output)

    @patch('scipfs.cli.Library')
    @patch('scipfs.cli.IPFSClient')
    def test_pin_library_empty_manifest_no_files(self, MockIPFSClient, MockLibrary):
        mock_ipfs_instance = MockIPFSClient.return_value
        mock_library_instance = MockLibrary.return_value

        mock_library_instance.name = "emptylib"
        mock_library_instance.manifest_path.exists.return_value = True
        mock_library_instance.manifest_cid = "QmEmptyManifestCID"
        mock_library_instance.list_files.return_value = []

        result = self.runner.invoke(cli, ['pin', 'library', 'emptylib'])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_ipfs_instance.pin.assert_called_once_with("QmEmptyManifestCID")
        self.assertIn("Library 'emptylib' contains no files to pin", result.output)

    @patch('scipfs.cli.IPFSClient')
    def test_pin_file_success(self, MockIPFSClient):
        mock_ipfs_instance = MockIPFSClient.return_value
        dummy_file_path_obj = TEST_CONFIG_DIR / "dummy_to_pin.txt"
        expected_cid = "QmDummyFileCID"

        with open(dummy_file_path_obj, "w") as f:
            f.write("test pin content")

        mock_ipfs_instance.add_file.return_value = expected_cid

        result = self.runner.invoke(cli, ['pin', 'file', str(dummy_file_path_obj)])
        
        dummy_file_path_obj.unlink()

        self.assertEqual(result.exit_code, 0, msg=result.output)
        mock_ipfs_instance.add_file.assert_called_once_with(dummy_file_path_obj, pin=True)
        self.assertIn(f"File '{dummy_file_path_obj.name}' added to IPFS with CID: {expected_cid}", result.output)
        self.assertIn(f"Successfully pinned CID: {expected_cid}", result.output)

if __name__ == '__main__':
    unittest.main() 