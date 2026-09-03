"""Enhanced tests for cloud provider with error handling."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.providers.cloud import CloudProvider


class TestCloudProviderRetry(unittest.TestCase):
    """Test cloud provider retry logic and error handling."""
    
    def test_successful_generation(self):
        """Cloud provider should return response on success."""
        mock_fn = MagicMock(return_value="Hello from cloud")
        provider = CloudProvider(mock_fn, max_retries=3)
        
        result = provider.generate("test prompt")
        
        self.assertEqual(result, "Hello from cloud")
        mock_fn.assert_called_once_with("test prompt")
    
    def test_retry_on_network_error(self):
        """Cloud provider should retry on network error."""
        mock_fn = MagicMock()
        mock_fn.side_effect = [
            urllib.error.URLError("Connection timeout"),
            urllib.error.URLError("Connection timeout"),
            "Success on third attempt"
        ]
        
        provider = CloudProvider(mock_fn, max_retries=3, retry_delay=0.01)
        result = provider.generate("test")
        
        self.assertEqual(result, "Success on third attempt")
        self.assertEqual(mock_fn.call_count, 3)
    
    def test_failure_after_retries(self):
        """Cloud provider should raise after exhausting retries."""
        mock_fn = MagicMock(side_effect=urllib.error.URLError("Connection failed"))
        provider = CloudProvider(mock_fn, max_retries=2, retry_delay=0.01)
        
        with self.assertRaises(RuntimeError) as context:
            provider.generate("test")
        
        self.assertIn("unavailable", str(context.exception))
        self.assertEqual(mock_fn.call_count, 2)
    
    def test_invalid_json_error(self):
        """Cloud provider should handle invalid JSON from response."""
        mock_fn = MagicMock(side_effect=json.JSONDecodeError("msg", "doc", 0))
        provider = CloudProvider(mock_fn, max_retries=1)
        
        with self.assertRaises(RuntimeError) as context:
            provider.generate("test")
        
        self.assertIn("invalid JSON", str(context.exception))
    
    def test_provider_name(self):
        """Cloud provider should have correct name."""
        provider = CloudProvider(lambda x: "test")
        self.assertEqual(provider.name, "cloud")


if __name__ == "__main__":
    unittest.main()
