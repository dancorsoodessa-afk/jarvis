import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import ipc
from agent.core import JarvisAgent


class EchoProvider:
    name = "echo"

    def generate(self, prompt: str) -> str:
        return f"echo:{prompt}"


def roundtrip(agent, requests):
    """Feed JSON-lines through serve_stream and parse the responses."""
    inp = io.StringIO("".join(json.dumps(r, ensure_ascii=False) + "\n"
                              for r in requests))
    out = io.StringIO()
    ipc.serve_stream(agent, inp, out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


class TestHandleRequest(unittest.TestCase):
    def setUp(self):
        self.agent = JarvisAgent(EchoProvider())

    def test_message(self):
        resp = ipc.handle_request(self.agent, {"id": 1, "type": "message", "text": "hi"})
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["text"], "echo:hi")
        self.assertEqual(resp["provider"], "echo")
        self.assertFalse(resp["needs_confirmation"])

    def test_tool_request(self):
        self.agent.tools.register("double", lambda n: int(n) * 2)
        resp = ipc.handle_request(self.agent,
                                  {"id": 2, "type": "tool", "tool": "double", "args": ["21"]})
        self.assertEqual(resp["text"], "42")
        self.assertEqual(resp["tool_used"], "double")

    def test_tools_listing(self):
        resp = ipc.handle_request(self.agent, {"id": 3, "type": "tools"})
        self.assertEqual(resp["tools"], [])

    def test_ping(self):
        self.assertEqual(ipc.handle_request(self.agent, {"type": "ping"})["type"], "pong")

    def test_errors_are_json_not_exceptions(self):
        for bad in ({"id": 4, "type": "message", "text": 123},
                    {"id": 5, "type": "tool", "tool": 7},
                    {"id": 6, "type": "nonsense"}):
            resp = ipc.handle_request(self.agent, bad)
            self.assertEqual(resp["type"], "error")
            self.assertEqual(resp["id"], bad["id"])

    def test_confirmation_over_ipc(self):
        self.agent.tools.register("wipe", lambda: "wiped", confirm=True)
        ask = ipc.handle_request(self.agent,
                                 {"id": 7, "type": "tool", "tool": "wipe"})
        self.assertTrue(ask["needs_confirmation"])
        done = ipc.handle_request(self.agent,
                                  {"id": 8, "type": "message", "text": "да"})
        self.assertEqual(done["text"], "wiped")


class TestServeStream(unittest.TestCase):
    def test_multiple_requests_and_bad_json(self):
        agent = JarvisAgent(EchoProvider())
        out = io.StringIO()
        ipc.serve_stream(agent, io.StringIO(
            '{"id": 1, "type": "ping"}\nnot json\n'
            '{"id": 2, "type": "message", "text": "ok"}\n'), out)
        responses = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual(responses[0]["type"], "pong")
        self.assertEqual(responses[1]["type"], "error")
        self.assertEqual(responses[2]["text"], "echo:ok")


class TestEndToEndSubprocess(unittest.TestCase):
    """Real binary path: python -m agent --ipc over pipes."""

    def test_ipc_subprocess(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ,
                   "JARVIS_MEMORY": str(Path(d) / "mem.json"),
                   "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
            proc = subprocess.Popen(
                [sys.executable, "-m", "agent", "--ipc"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, encoding="utf-8", env=env)
            self.addCleanup(proc.kill)
            try:
                proc.stdin.write('{"id": 0, "type": "tools"}\n')
                proc.stdin.write('{"id": 1, "type": "message", "text": "/status"}\n')
                proc.stdin.flush()
                tools_resp = json.loads(proc.stdout.readline())
                msg_resp = json.loads(proc.stdout.readline())
            finally:
                proc.kill()
        self.assertIn("status", tools_resp["tools"])
        self.assertIn("os", msg_resp["text"])


if __name__ == "__main__":
    unittest.main()
