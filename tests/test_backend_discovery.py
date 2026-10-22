import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from agent.config import DEFAULT_CHAT_URL, Settings, normalize_provider
from agent.core_router import discover_chat_endpoint


class TestBackendDiscovery(unittest.TestCase):
    def test_all_provider_aliases_are_pinned_to_huggingface(self):
        self.assertEqual(normalize_provider("dragon"), "huggingface")
        self.assertEqual(normalize_provider("dragon local"), "huggingface")
        self.assertEqual(normalize_provider("openrouter"), "huggingface")

    def test_settings_no_longer_hardcodes_ollama(self):
        settings = Settings.from_env()
        self.assertEqual(settings.provider, "huggingface")
        self.assertEqual(settings.chat_url, DEFAULT_CHAT_URL)

    def test_discovers_healthy_endpoint(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/v1/models":
                    body = json.dumps({"data": [{"id": "dragon-test-model"}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)

        endpoint = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        found, models = discover_chat_endpoint(endpoint, timeout=1.0)
        self.assertEqual(found, endpoint)
        self.assertEqual(models, ["dragon-test-model"])


if __name__ == "__main__":
    unittest.main()
