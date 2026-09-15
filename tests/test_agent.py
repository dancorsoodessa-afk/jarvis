        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from agent.providers.openai_chat import OpenAIChatProvider
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                response = handler(body)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response)
            def log_message(self, *a):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        registry = ToolRegistry()
        registry.register("double", lambda n: n * 2, description="Удвоить", parameters={"n": "число"})
        p = OpenAIChatProvider(url=f"http://127.0.0.1:{server.server_port}/v1", model="m", api_key="test-key")
        p.tool_executor = lambda name, args: "x"
        p.generate("hi", tools=registry.specs())
        self.assertEqual(seen["tools"][0]["function"]["name"], "double")


class TestTTS(unittest.TestCase):
    def test_off_by_default_raises(self):
        import os
        from agent import tts
        old = os.environ.get("JARVIS_TTS")
        os.environ["JARVIS_TTS"] = "off"
        try:
            with self.assertRaises(RuntimeError):
                tts.speak("тест")
            self.assertEqual(tts.current_engine(), "off")
        finally:
            if old is None:
                del os.environ["JARVIS_TTS"]
            else:
                os.environ["JARVIS_TTS"] = old
