import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import Settings
from agent.core import JarvisAgent
from agent.memory.store import MemoryStore
from agent.providers.local_vulkan import LocalVulkanProvider
from agent.tools import system
from agent.tools.registry import ConfirmationRequired, ToolRegistry


class EchoProvider:
    name = "echo"
    def generate(self, prompt: str) -> str:
        return f"echo:{prompt}"


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.id().replace(".", "_") + ".json")
        self.addCleanup(lambda: self.tmp.unlink(missing_ok=True))

    def make_agent(self, **kwargs):
        return JarvisAgent(EchoProvider(), memory=MemoryStore(self.tmp), **kwargs)

    def test_empty_message_greets(self):
        result = self.make_agent().handle("   ")
        self.assertEqual(result.provider, "echo")
        self.assertIn("?", result.text)

    def test_generate_and_memory(self):
        agent = self.make_agent()
        result = agent.handle("привет")
        self.assertEqual(result.text, "echo:привет")
        history = json.loads(self.tmp.read_text(encoding="utf-8"))["history"]
        self.assertEqual(history[-1]["user"], "привет")

    def test_tool_command(self):
        agent = self.make_agent()
        agent.tools.register("status", system.status)
        result = agent.handle("/status")
        self.assertEqual(result.tool_used, "status")
        self.assertIn("os", result.text)

    def test_unknown_tool(self):
        result = self.make_agent().handle("/nope")
        self.assertIn("Неизвестный инструмент", result.text)

    def test_confirmation_flow(self):
        agent = self.make_agent()
        agent.tools.register("wipe", lambda: "wiped", confirm=True)
        ask = agent.handle("/wipe")
        self.assertTrue(ask.needs_confirmation)
        self.assertNotIn("wiped", ask.text)
        done = agent.handle("да")
        self.assertEqual(done.text, "wiped")
        self.assertEqual(done.tool_used, "wipe")

    def test_registry_requires_confirmation(self):
        registry = ToolRegistry()
        registry.register("danger", lambda: "boom", confirm=True)
        with self.assertRaises(ConfirmationRequired):
            registry.call("danger")
        self.assertEqual(registry.call("danger", _confirmed=True), "boom")


class TestLocalVulkan(unittest.TestCase):
    def test_command_shape(self):
        provider = LocalVulkanProvider("llama-cli", "model.gguf", ctx=1024, threads=4)
        self.assertEqual(provider.name, "local-vulkan")
        self.assertIn("llama-cli", provider.llama_cli)

    def test_error_raises(self):
        provider = LocalVulkanProvider("false-binary-does-not-exist", "m.gguf")
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            provider.generate("hi")


class TestSettings(unittest.TestCase):
    def test_free_provider_is_default(self):
        settings = Settings.from_env()
        self.assertEqual(settings.provider, "openai-compatible")
        self.assertFalse(settings.use_local)


class TestOpenAIChatProvider(unittest.TestCase):
    def _provider(self, handler, **kwargs):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from agent.providers.openai_chat import OpenAIChatProvider

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = handler(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.handle_request, daemon=True).start()
        self.addCleanup(server.server_close)
        return OpenAIChatProvider(url=f"http://127.0.0.1:{server.server_port}/v1/chat/completions", api_key="test-key", model="test-model", **kwargs)

    def test_generate_parses_reply(self):
        def handler(body):
            req = json.loads(body)
            self.assertEqual(req["model"], "test-model")
            self.assertEqual(req["messages"][-1]["role"], "user")
            return json.dumps({"choices": [{"message": {"role": "assistant", "content": "Привет!"}}]}).encode()
        p = self._provider(handler)
        self.assertEqual(p.generate("тест"), "Привет!")
        self.assertEqual(len(p.history), 2)

    def test_error_raises_runtime(self):
        from agent.providers.openai_chat import OpenAIChatProvider
        p = OpenAIChatProvider(url="", model="m")
        with self.assertRaises(RuntimeError):
            p.generate("hi")

    def test_no_model_raises_runtime(self):
        from agent.providers.openai_chat import OpenAIChatProvider
        p = OpenAIChatProvider(url="http://127.0.0.1:1/v1", model="")
        with self.assertRaises(RuntimeError):
            p.generate("hi")


class TestFunctionCalling(unittest.TestCase):
    def _provider(self, responses):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from agent.providers.openai_chat import OpenAIChatProvider
        calls = {"n": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                i = min(calls["n"], len(responses) - 1)
                calls["n"] += 1
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(responses[i]).encode())
            def log_message(self, *a):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return OpenAIChatProvider(url=f"http://127.0.0.1:{server.server_port}/v1/chat/completions", api_key="k", model="m")

    def test_react_loop_executes_tool(self):
        tool_call = {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "double", "arguments": "{\"n\": \"21\"}"}}]}}]}
        final = {"choices": [{"message": {"role": "assistant", "content": "Ответ: 42"}}]}
        p = self._provider([tool_call, final])
        registry = ToolRegistry()
        registry.register("double", lambda n: int(n) * 2, description="Удвоить число", parameters={"n": "число"})
        agent = JarvisAgent(p, tools=registry)
        result = agent.handle("удвой 21")
        self.assertEqual(result.text, "Ответ: 42")
        self.assertEqual(p.history[-1]["content"], "Ответ: 42")

    def test_specs_sent_to_api(self):
        seen = {}
        def handler(body):
            seen.update(json.loads(body))
            return json.dumps({"choices": [{"message": {"role": "assistant", "content": "ok"}}]}).encode()
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
        p = OpenAIChatProvider(url=f"http://127.0.0.1:{server.server_port}/v1", model="m")
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

    def test_unknown_engine_raises(self):
        import os
        from agent import tts
        old = os.environ.get("JARVIS_TTS")
        os.environ["JARVIS_TTS"] = "nonexistent-engine"
        try:
            with self.assertRaises(RuntimeError):
                tts.speak("тест")
        finally:
            if old is None:
                del os.environ["JARVIS_TTS"]
            else:
                os.environ["JARVIS_TTS"] = old

    def test_say_tool_registered(self):
        from agent.runtime import build_agent
        agent = build_agent(Settings(provider="openai-compatible", chat_url="http://127.0.0.1:1/v1", chat_model="m"))
        self.assertIn("say", agent.tools.names())
        spec = agent.tools.spec("say")
        self.assertEqual(spec["function"]["name"], "say")
        self.assertIn("text", spec["function"]["parameters"]["properties"])


class TestStreamingIPC(unittest.TestCase):
    def test_sse_stream_parses_deltas_and_content(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from agent.providers.openai_chat import OpenAIChatProvider
        sse = ('data: {"choices":[{"delta":{"content":"При"}}]}\n\n'
               'data: {"choices":[{"delta":{"content":"вет"}}]}\n\n'
               'data: [DONE]\n\n')
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(sse.encode())
            def log_message(self, *a):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        p = OpenAIChatProvider(url=f"http://127.0.0.1:{server.server_port}/v1/chat/completions", api_key="k", model="m")
        deltas = []
        p.on_delta = deltas.append
        reply = p.generate("hi", tools=[{"type": "function", "function": {"name": "x"}}])
        self.assertEqual(reply, "Привет")
        self.assertEqual(deltas, ["При", "вет"])

    def test_ipc_emits_delta_events(self):
        import io
        from agent import ipc
        class StreamingEcho:
            name = "stream"
            def __init__(self):
                self.on_delta = None
                self.tool_executor = None
            def generate(self, prompt, tools=None, max_steps=6):
                if self.on_delta:
                    for word in ("один ", "два"):
                        self.on_delta(word)
                return "один два"
        agent = JarvisAgent(StreamingEcho())
        out = io.StringIO()
        inp = io.StringIO('{"id": 1, "type": "message", "text": "привет"}\n')
        ipc.serve_stream(agent, inp, out)
        lines = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual([l["type"] for l in lines], ["delta", "delta", "message"])
        self.assertEqual(lines[0]["text"], "один ")
        self.assertEqual(lines[-1]["text"], "один два")
