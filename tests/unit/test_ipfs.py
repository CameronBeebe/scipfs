import unittest
from unittest.mock import MagicMock, patch, call
import subprocess
import json
from pathlib import Path

try:
    from scipfs.ipfs import (
        IPFSClient, 
        SciPFSGoWrapperError, 
        IPFSConnectionError, 
        KuboVersionError,
        TimeoutError as SciPFSTimeoutError,
        SciPFSFileNotFoundError
    )
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scipfs.ipfs import (
        IPFSClient, 
        SciPFSGoWrapperError, 
        IPFSConnectionError, 
        KuboVersionError,
        TimeoutError as SciPFSTimeoutError,
        SciPFSFileNotFoundError
    )

class TestIPFSClient(unittest.TestCase):

    def setUp(self):
        self.api_addr = "/ip4/127.0.0.1/tcp/5001"
        # Patch _find_go_wrapper to avoid actual subprocess calls during most tests
        # We'll test _find_go_wrapper separately.
        self.patcher_find_wrapper = patch('scipfs.ipfs.IPFSClient._find_go_wrapper', return_value=None)
        self.mock_find_wrapper = self.patcher_find_wrapper.start()
        
        self.client = IPFSClient(api_addr=self.api_addr)
        # Simulate successful _find_go_wrapper for most tests
        self.client.go_wrapper_path = "/fake/path/to/scipfs_go_helper"
        self.client.go_wrapper_version = "0.1.0"

    def tearDown(self):
        self.patcher_find_wrapper.stop()

    def _mock_subprocess_run(self, stdout_data=None, stderr_data=None, return_code=0, side_effect=None):
        mock_proc = MagicMock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = return_code
        
        if stdout_data is not None:
            mock_proc.stdout = json.dumps(stdout_data) if isinstance(stdout_data, dict) else stdout_data
        else:
            mock_proc.stdout = ""
            
        if stderr_data is not None:
            mock_proc.stderr = json.dumps(stderr_data) if isinstance(stderr_data, dict) else stderr_data
        else:
            mock_proc.stderr = ""
        
        if side_effect:
            return MagicMock(side_effect=side_effect)
        return MagicMock(return_value=mock_proc)

    @patch('subprocess.run')
    def test_check_ipfs_daemon_success(self, mock_run):
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True, 
            "data": {"ID": "testpeerid", "Version": "0.23.0"}
        }).return_value # get the CompletedProcess mock

        self.client.required_version_tuple = (0, 23, 0)
        self.client.check_ipfs_daemon() # Should not raise
        self.assertEqual(self.client.daemon_version_str, "0.23.0")
        self.assertIsNotNone(self.client.client_id_dict)
        mock_run.assert_called_once_with(
            [self.client.go_wrapper_path, '-api', self.api_addr, 'daemon_info'], 
            capture_output=True, text=True, check=False, timeout=30, input=None
        )

    @patch('subprocess.run')
    def test_check_ipfs_daemon_connection_error(self, mock_run):
        # Simulate Go wrapper returning a connection error
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": False, 
            "error": "connection refused"
        }, return_code=0).return_value # Go wrapper ran, but reported failure
        
        with self.assertRaisesRegex(IPFSConnectionError, "connection refused"):
            self.client.check_ipfs_daemon()

    @patch('subprocess.run')
    def test_check_ipfs_daemon_version_mismatch(self, mock_run):
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True, 
            "data": {"ID": "testpeerid", "Version": "0.22.0"}
        }).return_value
        
        self.client.required_version_tuple = (0, 23, 0)
        with self.assertRaises(KuboVersionError):
            self.client.check_ipfs_daemon()

    @patch('subprocess.run')
    def test_add_json_success(self, mock_run):
        expected_cid = "QmAbc123"
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True, 
            "data": {"cid": expected_cid}
        }).return_value
        
        test_data = {"key": "value"}
        cid = self.client.add_json(test_data)
        self.assertEqual(cid, expected_cid)
        json_string_arg = json.dumps(test_data)
        mock_run.assert_called_once_with(
            [self.client.go_wrapper_path, '-api', self.api_addr, 'add_json'],
            capture_output=True, text=True, check=False, timeout=60, input=json_string_arg
        )
    
    @patch('subprocess.run')
    def test_get_json_success(self, mock_run):
        target_cid = "QmAbc123"
        expected_data = {"key": "value"}
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True, 
            "data": expected_data
        }).return_value

        data = self.client.get_json(target_cid)
        self.assertEqual(data, expected_data)
        mock_run.assert_called_once_with(
            [self.client.go_wrapper_path, '-api', self.api_addr, 'get_json_cid', '--cid', target_cid],
            capture_output=True, text=True, check=False, timeout=120, input=None
        )

    @patch('subprocess.run')
    def test_add_file_success_with_pin(self, mock_run):
        file_path = Path("test_file.txt")
        expected_cid = "QmXyZ789"
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True, 
            "data": {"cid": expected_cid}
        }).return_value

        with patch('pathlib.Path.is_file', return_value=True):
            cid = self.client.add_file(file_path, pin=True)
        
        self.assertEqual(cid, expected_cid)
        # Default is pin=true, so no --pin=false should be present
        self.assertNotIn("--pin", mock_run.call_args[0][0]) 
        self.assertIn(str(file_path), mock_run.call_args[0][0])

    @patch('subprocess.run')
    def test_add_file_success_no_pin(self, mock_run):
        file_path = Path("test_file_no_pin.txt")
        expected_cid = "QmNoPin123"
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True, 
            "data": {"cid": expected_cid}
        }).return_value

        with patch('pathlib.Path.is_file', return_value=True):
            cid = self.client.add_file(file_path, pin=False)
        
        self.assertEqual(cid, expected_cid)
        # Check that --pin false was passed
        self.assertIn("--pin", mock_run.call_args[0][0])
        self.assertIn("false", mock_run.call_args[0][0])

    @patch('subprocess.run')
    def test_execute_go_wrapper_command_json_go_failure(self, mock_run):
        # Go wrapper ran, but the command it executed (e.g. ipfs files stat) failed
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": False, 
            "error": "ipfs command failed: file not found"
        }, return_code=0).return_value

        with self.assertRaisesRegex(SciPFSGoWrapperError, "ipfs command failed: file not found"):
            self.client._execute_go_wrapper_command_json("some_command")

    @patch('subprocess.run')
    def test_execute_go_wrapper_command_json_process_error(self, mock_run):
        # Go wrapper itself failed to run properly
        mock_run.return_value = self._mock_subprocess_run(
            stderr_data="critical failure in go_helper", 
            return_code=1
        ).return_value

        with self.assertRaisesRegex(SciPFSGoWrapperError, "critical failure in go_helper"):
            self.client._execute_go_wrapper_command_json("some_command")
            
    @patch('subprocess.run')
    def test_execute_go_wrapper_command_json_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test_cmd", timeout=5)
        with self.assertRaisesRegex(SciPFSTimeoutError, "Timeout executing Go command"):
            self.client._execute_go_wrapper_command_json("some_command_timeout")

    @patch('subprocess.run')
    def test_get_pinned_cids(self, mock_run):
        expected_pin_cids = ["QmPin1", "QmPin2"]
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True,
            "data": {"cids": expected_pin_cids}
        }).return_value
        
        pins = self.client.get_pinned_cids(timeout=15)
        self.assertEqual(pins, set(expected_pin_cids))
        mock_run.assert_called_once_with(
            [self.client.go_wrapper_path, '-api', self.api_addr, 'list_pinned_cids', '--pin-type', 'all'],
            capture_output=True, text=True, check=False, timeout=15, input=None
        )

    @patch('subprocess.run')
    def test_find_providers_success(self, mock_run):
        cid_to_find = "QmToFind123"
        expected_providers = ["PeerID1", "PeerID2"]
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": True,
            "data": {"providers": expected_providers}
        }).return_value

        providers = self.client.find_providers(cid_to_find, timeout=30)
        self.assertEqual(providers, set(expected_providers))
        mock_run.assert_called_once_with(
            [self.client.go_wrapper_path, '-api', self.api_addr, 'dht_find_providers', '--cid', cid_to_find],
            capture_output=True, text=True, check=False, timeout=40, input=None # Overall timeout is correct
        )

    @patch('subprocess.run')
    def test_resolve_ipns_name_not_found(self, mock_run):
        ipns_name = "/ipns/kNonExistentKey"
        # Simulate go wrapper reporting a resolution failure
        mock_run.return_value = self._mock_subprocess_run(stdout_data={
            "success": False, 
            "error": "could not resolve name"
        }, return_code=0).return_value

        with self.assertRaisesRegex(SciPFSFileNotFoundError, "Could not resolve IPNS name"):
            self.client.resolve_ipns_name(ipns_name)

    # We need to unpatch _find_go_wrapper to test it directly
    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    @patch('os.access')
    def test_actual_find_go_wrapper_found_in_path(self, mock_os_access, mock_path_exists, mock_subprocess_run_for_find):
        # Stop the setUp class-level patch for this specific test method
        self.patcher_find_wrapper.stop()
    
        # IPFSClient.__init__ calls _find_go_wrapper, which will interact with the mocks.
        # We are primarily interested in the behavior of the explicit call to _find_go_wrapper below.
        client_for_find_test = IPFSClient(api_addr=self.api_addr)

        # Reset the mock and set up side_effect specifically for the call we are testing.
        mock_subprocess_run_for_find.reset_mock()
    
        expected_version = "0.1.0-test"
        mock_proc_success = MagicMock(spec=subprocess.CompletedProcess)
        mock_proc_success.returncode = 0
        mock_proc_success.stdout = json.dumps({"success": True, "data": {"version": expected_version}})
        mock_proc_success.stderr = ""

        mock_proc_fail_not_found = FileNotFoundError("Mocked: not found")

        mock_subprocess_run_for_find.side_effect = [
            mock_proc_fail_not_found,  # Fails for ./scipfs_go_helper
            mock_proc_fail_not_found,  # Fails for <package_path>/scipfs_go_helper
            mock_proc_success          # Succeeds for scipfs_go_helper (PATH)
        ]
        
        mock_path_exists.return_value = False 
        mock_os_access.return_value = True

        # Now call the method we actually want to test with the fresh mock setup
        client_for_find_test._find_go_wrapper() 
    
        self.assertEqual(client_for_find_test.go_wrapper_version, expected_version)
        self.assertEqual(client_for_find_test.go_wrapper_path, client_for_find_test.go_wrapper_executable_name)
        self.assertEqual(mock_subprocess_run_for_find.call_count, 3)
        calls = [
            call(['./scipfs_go_helper', 'version'], capture_output=True, text=True, check=False, timeout=5),
            call([str(Path('scipfs').resolve().parent / 'scipfs_go_helper'), 'version'], capture_output=True, text=True, check=False, timeout=5),
            call(['scipfs_go_helper', 'version'], capture_output=True, text=True, check=False, timeout=5)
        ]
        mock_subprocess_run_for_find.assert_has_calls(calls, any_order=False)

if __name__ == '__main__':
    unittest.main() 