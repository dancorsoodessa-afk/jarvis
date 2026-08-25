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
    def test_local_is_opt_in_by_default(self):
        self.assertFalse(Settings.from_env().use_local)


if __name__ == "__main__":
    unittest.main()
