"""Tests for web utilities."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools import web


class TestWebTools(unittest.TestCase):
    """Test web utility functions."""
    
    @patch("webbrowser.open")
    def test_open_url_valid(self, mock_browser):
        """open_url should open valid URLs in browser."""
        result = web.open_url("https://example.com")
        self.assertIn("example.com", result)
        mock_browser.assert_called_once_with("https://example.com")
    
    @patch("webbrowser.open")
    def test_open_url_no_scheme(self, mock_browser):
        """open_url should add https:// if missing."""
        result = web.open_url("example.com")
        self.assertIn("example.com", result)
        # Should have been called with https://
        call_args = mock_browser.call_args[0][0]
        self.assertTrue(call_args.startswith("https://"))
    
    def test_open_url_empty(self):
        """open_url should reject empty URL."""
        with self.assertRaises(ValueError):
            web.open_url("")
    
    @patch("urllib.request.urlopen")
    def test_get_webpage_title_found(self, mock_urlopen):
        """get_webpage_title should extract title from HTML."""
        mock_response = MagicMock()
        mock_response.headers.get.return_value = "text/html"
        mock_response.read.return_value = b"<html><head><title>Test Page</title></head></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        result = web.get_webpage_title("https://example.com")
        self.assertEqual(result, "Test Page")
    
    def test_get_webpage_title_empty(self):
        """get_webpage_title should reject empty URL."""
        with self.assertRaises(ValueError):
            web.get_webpage_title("")
    
    def test_search_web_empty_query(self):
        """search_web should reject empty query."""
        with self.assertRaises(ValueError):
            web.search_web("")
    
    def test_search_web_whitespace_query(self):
        """search_web should reject whitespace-only query."""
        with self.assertRaises(ValueError):
            web.search_web("   ")


if __name__ == "__main__":
    unittest.main()
