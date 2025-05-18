#!/usr/bin/env python3
import unittest
import tempfile
from pathlib import Path
from scipfs.ipfs import IPFSClient, RuntimeError, FileNotFoundError, SciPFSGoWrapperError

class TestIPNSOperations(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.client = IPFSClient()
        self.test_key_name = "test_key"
        
        # Create a test file for publishing
        self.test_dir = tempfile.mkdtemp()
        self.test_file = Path(self.test_dir) / "test.txt"
        self.test_content = b"Hello, IPNS!"
        self.test_file.write_bytes(self.test_content)
        
    def tearDown(self):
        """Clean up test fixtures after each test method."""
        # Clean up test directory
        import shutil
        shutil.rmtree(self.test_dir)

        # Remove the test IPNS key if it exists
        # try:
        #     keys = self.client.list_ipns_keys()
        #     if any(k['Name'] == self.test_key_name for k in keys):
        #         # self.client.client.key.rm(self.test_key_name) # This line caused error as self.client.client is None
        #         # Key removal is not part of the current Go wrapper migration scope.
        #         pass # If key removal was implemented, it would be called here.
        # except Exception as e:
        #     # Log or print the exception if needed, but don't let it fail teardown
        #     print(f"Error during IPNS key cleanup: {e}")
        
    def test_generate_ipns_key_success(self):
        """Test successful IPNS key generation."""
        # 1. Generate a new key
        key_info = self.client.generate_ipns_key(self.test_key_name)
        
        # 2. Verify key info is returned
        self.assertIsNotNone(key_info, "No key info returned")
        self.assertIn('Name', key_info, "Key info missing 'Name'")
        self.assertIn('Id', key_info, "Key info missing 'Id'")
        self.assertEqual(key_info['Name'], self.test_key_name,
                        "Key name does not match requested name")
        
        # 3. Verify key exists in list
        keys = self.client.list_ipns_keys()
        self.assertTrue(any(k['Name'] == self.test_key_name for k in keys),
                       "Generated key not found in key list")
        
    def test_generate_ipns_key_duplicate(self):
        """Test generating a key that already exists."""
        # 1. Generate a key
        key_info = self.client.generate_ipns_key(self.test_key_name)
        self.assertIsNotNone(key_info, "Failed to generate initial key")
        
        # 2. Try to generate same key again
        # This should return the existing key info
        duplicate_key_info = self.client.generate_ipns_key(self.test_key_name)
        
        # 3. Verify appropriate behavior
        self.assertIsNotNone(duplicate_key_info, "No key info returned for duplicate key")
        self.assertEqual(duplicate_key_info['Id'], key_info['Id'],
                        "Duplicate key has different ID")
        
    def test_list_ipns_keys(self):
        """Test listing IPNS keys."""
        # 1. Generate a test key
        key_info = self.client.generate_ipns_key(self.test_key_name)
        self.assertIsNotNone(key_info, "Failed to generate test key")
        
        # 2. List keys
        keys = self.client.list_ipns_keys()
        
        # 3. Verify test key is in list
        self.assertTrue(any(k['Name'] == self.test_key_name for k in keys),
                       "Test key not found in key list")
        
    def test_check_key_exists(self):
        """Test checking if a key exists."""
        # 1. Generate a test key
        key_info = self.client.generate_ipns_key(self.test_key_name)
        self.assertIsNotNone(key_info, "Failed to generate test key")
        
        # 2. Check if it exists
        self.assertTrue(self.client.check_key_exists(self.test_key_name),
                       "Generated key not found by check_key_exists")
        
        # 3. Check if non-existent key exists
        self.assertFalse(self.client.check_key_exists("nonexistent_key"),
                        "Non-existent key reported as existing")
        
    def test_publish_to_ipns_success(self):
        """Test successful IPNS publishing."""
        # 1. Generate a test key
        key_info = self.client.generate_ipns_key(self.test_key_name)
        self.assertIsNotNone(key_info, "Failed to generate test key")
        
        # 2. Add a test file
        cid = self.client.add_file(self.test_file)
        self.assertIsNotNone(cid, "Failed to add test file")
        
        # 3. Publish file CID to IPNS
        publish_result = self.client.publish_to_ipns(self.test_key_name, cid)
        
        # 4. Verify publish result
        self.assertIsNotNone(publish_result, "No publish result returned")
        self.assertIn('Name', publish_result, "Publish result missing 'Name'")
        self.assertEqual(publish_result['Name'], key_info['Id'],
                        "Published IPNS key ID does not match original key ID")
        self.assertIn('Value', publish_result, "Publish result missing 'Value'")
        expected_value_path = cid if cid.startswith('/ipfs/') else f"/ipfs/{cid}"
        self.assertEqual(publish_result['Value'], expected_value_path,
                         "Published IPNS value does not match target CID path")
        
    def test_publish_to_ipns_nonexistent_key(self):
        """Test publishing with a non-existent key."""
        # 1. Use a non-existent key name
        nonexistent_key = "nonexistent_key_63527" # Made more unique
        
        # 2. Add a test file
        cid = self.client.add_file(self.test_file)
        self.assertIsNotNone(cid, "Failed to add test file")
        
        # 3. Attempt to publish
        with self.assertRaises(SciPFSGoWrapperError) as context:
            self.client.publish_to_ipns(nonexistent_key, cid)
            
        # 4. Verify appropriate error is raised
        self.assertIn("no key by the given name was found", str(context.exception).lower())
        
    def test_resolve_ipns_name_success(self):
        """Test successful IPNS name resolution."""
        # 1. Generate a test key
        key_info = self.client.generate_ipns_key(self.test_key_name)
        self.assertIsNotNone(key_info, "Failed to generate test key")
        
        # 2. Add a test file
        cid = self.client.add_file(self.test_file)
        self.assertIsNotNone(cid, "Failed to add test file")
        
        # 3. Publish file CID to IPNS
        publish_result = self.client.publish_to_ipns(self.test_key_name, cid)
        self.assertIsNotNone(publish_result, "Failed to publish to IPNS")
        
        # 4. Resolve IPNS name
        ipns_name = f"/ipns/{key_info['Id']}"
        resolved_path = self.client.resolve_ipns_name(ipns_name)
        
        # 5. Verify resolved path
        self.assertIsNotNone(resolved_path, "No resolved path returned")
        self.assertTrue(resolved_path.startswith("/ipfs/"),
                       "Resolved path does not start with /ipfs/")
        
    def test_resolve_ipns_name_nonexistent(self):
        """Test resolving a non-existent IPNS name."""
        # 1. Use a non-existent IPNS name
        nonexistent_ipns = "/ipns/QmNonExistentKey123456789"
        
        # 2. Attempt to resolve
        with self.assertRaises(FileNotFoundError) as context:
            self.client.resolve_ipns_name(nonexistent_ipns)
            
        # 3. Verify appropriate error is raised
        self.assertIn("Could not resolve IPNS name", str(context.exception))

if __name__ == '__main__':
    unittest.main() 