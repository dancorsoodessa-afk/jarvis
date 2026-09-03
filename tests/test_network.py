"""Tests for network utilities."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools import network


class TestNetworkTools(unittest.TestCase):
    """Test network utility functions."""
    
    def test_check_internet_returns_dict(self):
        """check_internet should return dict with 'connected' and 'details'."""
        result = network.check_internet()
        self.assertIsInstance(result, dict)
        self.assertIn("connected", result)
        self.assertIn("details", result)
        self.assertIsInstance(result["connected"], bool)
    
    @patch("subprocess.run")
    def test_ping_valid_host(self, mock_run):
        """ping should execute for valid hosts."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="PING google.com (8.8.8.8) ... \n64 bytes from ...\n4 packets transmitted"
        )
        
        result = network.ping("google.com")
        self.assertIsInstance(result, str)
        mock_run.assert_called_once()
    
    def test_ping_invalid_host_empty(self):
        """ping should reject empty host."""
        with self.assertRaises(ValueError):
            network.ping("")
    
    def test_ping_invalid_host_injection(self):
        """ping should reject hosts with shell metacharacters."""
        invalid_hosts = [
            "host; rm -rf /",
            "host | cat /etc/passwd",
            "host && echo hacked",
            "host $(whoami)",
        ]
        
        for host in invalid_hosts:
            with self.assertRaises(ValueError):
                network.ping(host)
    
    @patch("subprocess.run")
    def test_ping_timeout_handling(self, mock_run):
        """ping should handle command timeouts gracefully."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("ping", 5)
        
        with self.assertRaises(RuntimeError):
            network.ping("example.com")
    
    @patch("subprocess.run")
    def test_get_dns_windows(self, mock_run):
        """get_dns should work on Windows."""
        mock_run.return_value = MagicMock(
            stdout="DNS Servers . . . . . . . . . . . . : 8.8.8.8\n"
        )
        
        result = network.get_dns()
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
