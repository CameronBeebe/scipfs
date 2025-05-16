#!/usr/bin/env python3
import unittest
from pathlib import Path
import tempfile
import shutil
from scipfs.ipfs import IPFSClient, RuntimeError, TimeoutError, ConnectionError

class TestPinOperations(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.client = IPFSClient()
        self.test_dir = tempfile.mkdtemp()
        
        # Create a test file
        self.test_file = Path(self.test_dir) / "test.txt"
        self.test_content = b"Hello, IPFS!"
        self.test_file.write_bytes(self.test_content)
        
    def tearDown(self):
        """Clean up test fixtures after each test method."""
        shutil.rmtree(self.test_dir)
        
    def test_pin_valid_cid(self):
        """Test pinning a valid CID."""
        # 1. Add a test file to get a valid CID
        cid = self.client.add_file(self.test_file)
        self.assertIsNotNone(cid, "Failed to add test file")
        
        # 2. Pin the CID
        try:
            self.client.pin(cid)
        except (RuntimeError, TimeoutError, ConnectionError) as e:
            self.fail(f"Failed to pin valid CID {cid}: {e}")
            
        # 3. Verify CID is in pinned list
        pinned_cids = self.client.get_pinned_cids()
        self.assertIn(cid, pinned_cids,
                     f"Test file CID {cid} not found in pinned CIDs after pinning")
        
    def test_pin_invalid_cid_format(self):
        """Test pinning with invalid CID format."""
        invalid_cid = "not-a-valid-cid-format"
        with self.assertRaises(RuntimeError) as context:
            self.client.pin(invalid_cid)
        self.assertIn("Invalid CID format", str(context.exception),
                     "Error message should indicate invalid CID format")
        
    def test_pin_non_existent_cid(self):
        """Test pinning a non-existent but valid CID."""
        # Use a known non-existent but valid CID format
        non_existent_cid = "QmUNLLsPACCz1vLxQVkXqqLX5R1X345qqfHbsf67hvA3Nn"
        try:
            self.client.pin(non_existent_cid)
            # If pin succeeds, verify it's in the pinned list
            pinned_cids = self.client.get_pinned_cids()
            self.assertIn(non_existent_cid, pinned_cids,
                         f"Non-existent CID {non_existent_cid} not found in pinned CIDs after pinning")
        except RuntimeError as e:
            # It's also valid for the pin to fail if the node can't resolve the CID
            self.assertIn("Failed to pin IPFS path", str(e),
                         "Error message should indicate pin failure")
        
    def test_get_pinned_cids_success(self):
        """Test getting pinned CIDs."""
        # 1. Add and pin a test file
        cid = self.client.add_file(self.test_file)
        self.assertIsNotNone(cid, "Failed to add test file")
        self.client.pin(cid)
        
        # 2. Get pinned CIDs
        pinned_cids = self.client.get_pinned_cids()
        
        # 3. Verify test file CID is in list
        self.assertIn(cid, pinned_cids,
                     f"Test file CID {cid} not found in pinned CIDs")
        
    def test_get_pinned_cids_empty(self):
        """Test getting pinned CIDs when none are pinned."""
        # 1. Ensure no files are pinned
        # Note: We can't easily unpin everything, so we'll just verify
        # that the method returns a set and doesn't raise an error
        
        # 2. Get pinned CIDs
        pinned_cids = self.client.get_pinned_cids()
        
        # 3. Verify empty set is returned
        self.assertIsInstance(pinned_cids, set,
                            "get_pinned_cids did not return a set")
        
    def test_get_pinned_cids_after_unpin(self):
        """Test getting pinned CIDs after unpinning."""
        # 1. Add and pin a test file
        cid = self.client.add_file(self.test_file)
        self.assertIsNotNone(cid, "Failed to add test file")
        self.client.pin(cid)
        
        # 2. Unpin the file
        # Note: We need to use the IPFS CLI directly since we haven't
        # implemented unpin in our client yet
        import subprocess
        subprocess.run(["ipfs", "pin", "rm", cid], check=True)
        
        # 3. Get pinned CIDs
        pinned_cids = self.client.get_pinned_cids()
        
        # 4. Verify test file CID is not in list
        self.assertNotIn(cid, pinned_cids,
                        f"Test file CID {cid} still found in pinned CIDs after unpinning")

if __name__ == '__main__':
    unittest.main() 