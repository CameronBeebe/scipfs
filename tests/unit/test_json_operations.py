#!/usr/bin/env python3
import unittest
import json
import tempfile
from pathlib import Path
from scipfs.ipfs import IPFSClient, RuntimeError, SciPFSException
import ipfshttpclient
import logging

logger = logging.getLogger(__name__)

class TestJsonOperations(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.client = IPFSClient()
        self.test_data = {
            "name": "test",
            "value": 42,
            "nested": {
                "key": "value"
            }
        }
        
    def test_add_json_success(self):
        """Test successful JSON addition."""
        # 1. Add test JSON data
        cid = self.client.add_json(self.test_data)
        
        # 2. Verify CID is returned
        self.assertIsNotNone(cid, "No CID returned from add_json")
        
        # 3. Verify CID is valid format (starts with Qm)
        self.assertTrue(cid.startswith("Qm"), 
                       f"Invalid CID format: {cid}")
        
    def test_get_json_success(self):
        """Test successful JSON retrieval."""
        # 1. Add test JSON data
        cid = self.client.add_json(self.test_data)
        self.assertIsNotNone(cid, "Failed to add test JSON")
        
        # 2. Retrieve JSON using get_json
        retrieved_data = self.client.get_json(cid)
        
        # 3. Verify retrieved data matches original
        self.assertEqual(retrieved_data, self.test_data,
                        "Retrieved JSON does not match original")
        
    def test_get_json_nonexistent_cid(self):
        """Test getting JSON with a non-existent CID."""
        nonexistent_cid = "QmNonExistentCID123456789"
        # Expecting SciPFSException (wrapping ErrorResponse) when CID not found
        with self.assertRaises(SciPFSException) as cm:
            self.client.get_json(nonexistent_cid)
        self.assertIn(f"IPFS error retrieving JSON for CID {nonexistent_cid}", str(cm.exception))
        self.assertTrue(isinstance(cm.exception.__cause__, ipfshttpclient.exceptions.ErrorResponse))
        
    def test_get_json_invalid_json(self):
        """Test getting invalid JSON content."""
        # 1. Add content that is not JSON to IPFS
        non_json_content = "This is not JSON."
        cid = self.client.client.add_bytes(non_json_content.encode('utf-8')) # Using underlying client.add_bytes
        self.client.pin(cid) # Pin it via our IPFSClient.pin (which uses Go wrapper)
        
        # 2. Attempt to get the content as JSON
        # Expecting SciPFSException (wrapping JSONDecodeError)
        with self.assertRaises(SciPFSException) as cm:
            self.client.get_json(cid)
        self.assertIn(f"Content for CID {cid} is not valid JSON.", str(cm.exception))
        self.assertTrue(isinstance(cm.exception.__cause__, json.JSONDecodeError))
        
        # Clean up by unpinning using the underlying ipfshttpclient's pin.rm method
        try:
            self.client.client.pin.rm(cid)
            logger.info(f"Test cleanup: Unpinned CID {cid} using ipfshttpclient.")
        except ipfshttpclient.exceptions.ErrorResponse as e:
            # If unpinning fails (e.g., not pinned or other IPFS issue), log it but don't fail the test
            logger.warning(f"Test cleanup: Failed to unpin CID {cid} using ipfshttpclient: {e}")

if __name__ == '__main__':
    unittest.main() 