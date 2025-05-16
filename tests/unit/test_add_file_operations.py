#!/usr/bin/env python3
import unittest
from pathlib import Path
import tempfile
import shutil
from scipfs.ipfs import IPFSClient, FileNotFoundError, ConnectionError, RuntimeError, TimeoutError

class TestAddFileOperations(unittest.TestCase):
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
        
    def test_add_file_success(self):
        """Test successful file addition."""
        # 1. Add the test file
        cid = self.client.add_file(self.test_file)
        
        # 2. Verify CID is returned and valid
        self.assertIsNotNone(cid, "No CID returned from add_file")
        self.assertTrue(cid.startswith("Qm"), 
                       f"Invalid CID format: {cid}")
        
        # 3. Verify file can be retrieved
        output_path = Path(self.test_dir) / "downloaded.txt"
        self.client.get_file(cid, output_path)
        self.assertTrue(output_path.exists(), "Downloaded file does not exist")
        downloaded_content = output_path.read_bytes()
        self.assertEqual(downloaded_content, self.test_content,
                        "Downloaded content does not match original")
        
    def test_add_file_nonexistent(self):
        """Test adding a non-existent file."""
        nonexistent_file = Path(self.test_dir) / "nonexistent.txt"
        with self.assertRaises(FileNotFoundError) as context:
            self.client.add_file(nonexistent_file)
        self.assertIn("File not found", str(context.exception))
        
    def test_add_file_empty(self):
        """Test adding an empty file."""
        empty_file = Path(self.test_dir) / "empty.txt"
        empty_file.touch()
        
        cid = self.client.add_file(empty_file)
        self.assertIsNotNone(cid, "No CID returned for empty file")
        self.assertTrue(cid.startswith("Qm"),
                       f"Invalid CID format for empty file: {cid}")
        
    def test_add_file_large(self):
        """Test adding a large file."""
        large_file = Path(self.test_dir) / "large.txt"
        # Create a 1MB file
        with open(large_file, "wb") as f:
            f.write(b"0" * 1024 * 1024)
            
        try:
            cid = self.client.add_file(large_file)
            self.assertIsNotNone(cid, "No CID returned for large file")
            self.assertTrue(cid.startswith("Qm"),
                          f"Invalid CID format for large file: {cid}")
        except TimeoutError:
            self.fail("Timeout while adding large file")
        except Exception as e:
            self.fail(f"Unexpected error adding large file: {e}")

if __name__ == '__main__':
    unittest.main() 