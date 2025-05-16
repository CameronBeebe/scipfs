#!/usr/bin/env python3
import unittest
import sys
import os
import argparse

def run_tests(test_type='all', verbosity=2):
    """Run tests in the specified test directory.
    
    Args:
        test_type (str): Type of tests to run ('unit', 'integration', or 'all')
        verbosity (int): Test runner verbosity level (1-3)
    """
    # Add the project root to the Python path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)
    
    # Discover and run tests in the specified directory
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    if test_type in ['unit', 'all']:
        unit_dir = os.path.join(project_root, 'tests', 'unit')
        unit_suite = loader.discover(unit_dir, pattern='test_*.py', top_level_dir=project_root)
        suite.addTest(unit_suite)
        
    if test_type in ['integration', 'all']:
        integration_dir = os.path.join(project_root, 'tests', 'integration')
        # For integration tests, we'll look for both .py and .sh files
        integration_suite = loader.discover(integration_dir, pattern='test_*.py', top_level_dir=project_root)
        suite.addTest(integration_suite)
        # Note: Shell script tests would need to be run separately
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    # Return non-zero exit code if tests failed
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run SciPFS tests')
    parser.add_argument('--type', choices=['unit', 'integration', 'all'],
                      default='all', help='Type of tests to run')
    parser.add_argument('--verbosity', type=int, choices=[1, 2, 3],
                      default=2, help='Test runner verbosity level')
    args = parser.parse_args()
    
    sys.exit(run_tests(args.type, args.verbosity)) 