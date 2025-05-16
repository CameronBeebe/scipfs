#!/usr/bin/env python3
import unittest
from pathlib import Path
import tempfile
import shutil
import os
from scipfs.ipfs import IPFSClient, FileNotFoundError, RuntimeError
import ipfshttpclient.exceptions

class TestGetFile(unittest.TestCase):
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
        
    def test_get_file_success(self):
        """Test successful file download."""
        # 1. Add a test file to IPFS
        cid = self.client.add_file(self.test_file)
        self.assertIsNotNone(cid, "Failed to add test file to IPFS")
        
        # 2. Download it using get_file
        output_path = Path(self.test_dir) / "downloaded.txt"
        self.client.get_file(cid, output_path)
        
        # 3. Verify the downloaded file matches the original
        self.assertTrue(output_path.exists(), "Downloaded file does not exist")
        downloaded_content = output_path.read_bytes()
        self.assertEqual(downloaded_content, self.test_content, 
                        "Downloaded content does not match original")
        
    def test_get_file_nonexistent_cid(self):
        """Test getting a file with a non-existent CID."""
        nonexistent_cid = "QmNonExistentCID123456789"
        output_path = Path(self.test_dir) / "nonexistent.txt"
        # Expecting ErrorResponse when the CID is not found by ipfs cat
        with self.assertRaises(ipfshttpclient.exceptions.ErrorResponse) as cm:
            self.client.get_file(nonexistent_cid, output_path)
        self.assertIn("path does not have enough components", str(cm.exception)) # Or more specific error check
        self.assertFalse(output_path.exists())
        
    def test_get_file_invalid_cid(self):
        """Test getting a file with an invalid CID format."""
        invalid_cid = "not-a-valid-cid"
        output_path = Path(self.test_dir) / "invalid.txt"
        # Expecting ErrorResponse when the CID format is invalid for ipfs cat
        with self.assertRaises(ipfshttpclient.exceptions.ErrorResponse) as cm:
            self.client.get_file(invalid_cid, output_path)
        self.assertIn("path does not have enough components", str(cm.exception)) # Or more specific error check
        self.assertFalse(output_path.exists())

if __name__ == '__main__':
    unittest.main() 