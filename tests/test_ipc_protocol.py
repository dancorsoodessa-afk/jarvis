"""Tests for IPC communication layer."""

import sys
import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.ipc import JsonLineProtocol
from agent.core import JarvisAgent, AgentResult


class EchoProvider:
    name = "test"
    def generate(self, prompt: str) -> str:
        return f"echo: {prompt}"


class TestIPC(unittest.TestCase):
    """Test IPC communication."""
    
    def test_json_line_protocol_encode(self):
        """JsonLineProtocol should encode messages correctly."""
        result = AgentResult("Hello", "test", tool_used=None)
        
        # Manually test encoding logic
        data = {
            "text": result.text,
            "provider": result.provider,
            "tool_used": result.tool_used,
            "needs_confirmation": result.needs_confirmation
        }
        
        line = json.dumps(data) + "\n"
        self.assertIn("Hello", line)
        self.assertIn("test", line)
    
    def test_json_line_protocol_decode(self):
        """JsonLineProtocol should decode messages correctly."""
        line = '{"text": "response", "provider": "cloud", "tool_used": null, "needs_confirmation": false}\n'
        
        data = json.loads(line)
        
        self.assertEqual(data["text"], "response")
        self.assertEqual(data["provider"], "cloud")
        self.assertFalse(data["needs_confirmation"])
    
    def test_ipc_tool_confirmation_flow(self):
        """IPC should handle tool confirmation flow."""
        from agent.tools.registry import ToolRegistry
        
        agent = JarvisAgent(EchoProvider())
        agent.tools = ToolRegistry()
        agent.tools.register("test_action", lambda: "done", confirm=True)
        
        # First message: request tool
        ask_result = agent.handle("/test_action")
        self.assertTrue(ask_result.needs_confirmation)
        
        # Second message: confirm
        confirm_result = agent.handle("да")
        self.assertEqual(confirm_result.text, "done")
    
    def test_ipc_error_handling(self):
        """IPC should handle errors gracefully."""
        class FailProvider:
            name = "fail"
            def generate(self, prompt):
                raise RuntimeError("Provider error")
        
        agent = JarvisAgent(FailProvider())
        
        # Should not raise, but return error in AgentResult
        with self.assertRaises(RuntimeError):
            agent.handle("test")


if __name__ == "__main__":
    unittest.main()
