#!/usr/bin/env python3
import unittest
import json
import tempfile
from pathlib import Path
from scipfs.ipfs import IPFSClient, SciPFSGoWrapperError, SciPFSException
import logging

logger = logging.getLogger(__name__)

class TestJsonOperations(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.client = IPFSClient()
        self.test_data = {"name": "test_json", "value": 42}
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures after each test method."""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_add_json_success(self):
        """Test successful JSON addition."""
        # 1. Add test JSON data
        cid = self.client.add_json(self.test_data)
    
        # 2. Verify CID is returned
        self.assertIsNotNone(cid, "No CID returned from add_json")
    
        # 3. Verify CID is valid format (starts with bafk for CIDv1)
        self.assertTrue(cid.startswith("bafk"), # Updated for CIDv1
                       f"Invalid CID format: {cid}")
        
    def test_get_json_success(self):
        """Test successful JSON retrieval."""
        # 1. Add test JSON data
        cid = self.client.add_json(self.test_data)
        self.assertIsNotNone(cid, "Failed to add test JSON for get_json test")
        
        # 2. Get JSON data
        retrieved_data = self.client.get_json(cid)
        
        # 3. Verify retrieved data matches original data
        self.assertEqual(retrieved_data, self.test_data,
                        "Retrieved JSON data does not match original data")
        
    def test_get_json_nonexistent_cid(self):
        """Test getting JSON with a non-existent or invalid CID."""
        nonexistent_cid = "QmNonExistentCIDTooShort" # Invalidly formatted CID
        with self.assertRaises(SciPFSGoWrapperError) as cm: # Updated exception type
            self.client.get_json(nonexistent_cid)
        # Check for part of the new error message from Go helper
        self.assertIn("invalid cid", str(cm.exception).lower()) 

    def test_get_json_invalid_json(self):
        """Test getting content that is not JSON and expecting a parse error."""
        # 1. Add content that is not JSON to IPFS using add_file
        non_json_content = "This is not valid JSON content."
        temp_file_path = Path(self.test_dir) / "not_json.txt"
        temp_file_path.write_text(non_json_content)
        
        cid = self.client.add_file(temp_file_path)
        self.assertIsNotNone(cid, "Failed to add non-JSON file for the test")
        
        # 2. Attempt to get it as JSON
        # Expecting SciPFSGoWrapperError because Go helper's json.Unmarshal will fail
        with self.assertRaises(SciPFSGoWrapperError) as cm:
            self.client.get_json(cid)
        
        # 3. Verify appropriate error is raised (e.g., JSON parsing error from Go)
        self.assertIn("failed to unmarshal json", str(cm.exception).lower(),
                      f"Unexpected error message: {str(cm.exception)}")

if __name__ == '__main__':
    unittest.main() 