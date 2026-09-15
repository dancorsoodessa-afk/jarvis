import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core import JarvisAgent
from agent.providers.openai_chat import OpenAIChatProvider
from agent.tools.registry import ToolRegistry


class TestModelConfirmation(unittest.TestCase):
    def test_model_requested_dangerous_tool_stops_for_confirmation(self):
        responses = [
            {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "wipe", "arguments": "{}"}}
            ]}}]},
            {"choices": [{"message": {"role": "assistant", "content": "Это уже выполнено"}}]},
        ]
        calls = {"n": 0}
        executed = {"value": False}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                i = min(calls["n"], len(responses) - 1)
                calls["n"] += 1
                body = json.dumps(responses[i]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        provider = OpenAIChatProvider(
            url=f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
            model="test-model",
            api_key="test-key",
        )
        registry = ToolRegistry()
        registry.register(
            "wipe",
            lambda: executed.__setitem__("value", True) or "wiped",
            confirm=True,
            description="Опасное удаление",
        )
        agent = JarvisAgent(provider, tools=registry)

        ask = agent.handle("удали всё")
        self.assertTrue(ask.needs_confirmation)
        self.assertIn("требует подтверждения", ask.text)
        self.assertFalse(executed["value"])
        self.assertEqual(calls["n"], 1)

        done = agent.handle("да")
        self.assertEqual(done.text, "wiped")
        self.assertTrue(executed["value"])


if __name__ == "__main__":
    unittest.main()
