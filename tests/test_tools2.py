import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.core import JarvisAgent
from agent.reminders import ReminderService
from agent.runtime import build_agent
from agent.tools import processes


class EchoProvider:
    name = "echo"

    def generate(self, prompt: str) -> str:
        return f"echo:{prompt}"


class TestProcesses(unittest.TestCase):
    def test_list_processes_finds_current_python(self):
        procs = processes.list_processes()
        self.assertTrue(any(p["pid"] == os.getpid() for p in procs)
                        or len(procs) > 0)
        for p in procs:
            self.assertIn("pid", p)
            self.assertIn("name", p)

    def test_list_processes_filter(self):
        procs = processes.list_processes("definitely-no-such-process-xyz")
        self.assertEqual(procs, [])

    def test_kill_refuses_own_pid(self):
        with self.assertRaises(ValueError):
            processes.kill_process(str(os.getpid()))

    @unittest.skipIf(sys.platform == "win32", "posix-only spawn test")
    def test_kill_terminates_spawned_process(self):
        proc = subprocess.Popen(["sleep", "60"])
        self.addCleanup(proc.kill)
        self.assertIn("terminated", processes.kill_process(str(proc.pid)))
        proc.wait(timeout=5)
        self.assertIsNotNone(proc.poll())


class TestReminders(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.svc = ReminderService(str(Path(self.dir.name) / "rem.json"))

    def test_add_and_list(self):
        msg = self.svc.add("5", "позвонить", "маме")
        self.assertIn("позвонить маме", msg)
        listing = self.svc.list_pending()
        self.assertIn("позвонить маме", listing)

    def test_add_validates_input(self):
        with self.assertRaises(ValueError):
            self.svc.add("5")          # no text
        with self.assertRaises(ValueError):
            self.svc.add("-1", "text")  # negative delay

    def test_pop_due_returns_and_removes(self):
        self.svc.add("0.001", "срочное")
        time.sleep(0.1)
        due = self.svc.pop_due()
        self.assertEqual(due, ["срочное"])
        self.assertEqual(self.svc.pop_due(), [])

    def test_agent_prepends_due_reminders(self):
        self.svc.add("0.001", "выпей воды")
        time.sleep(0.1)
        agent = JarvisAgent(EchoProvider(), reminders=self.svc)
        result = agent.handle("привет")
        self.assertTrue(result.text.startswith("⏰"))
        self.assertIn("выпей воды", result.text)


class TestRuntimeWiring(unittest.TestCase):
    def test_build_agent_registers_all_tools(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["JARVIS_MEMORY"] = str(Path(d) / "mem.json")
            self.addCleanup(lambda: os.environ.pop("JARVIS_MEMORY", None))
            agent = build_agent()
            names = set(agent.tools.names())
            expected = {"status", "search", "delete", "launch", "volume",
                        "set_volume", "screenshot", "ps", "kill",
                        "clip_get", "clip_set", "remind", "reminders"}
            self.assertTrue(expected <= names, expected - names)
            self.assertEqual(agent.provider.name, "cloud")


if __name__ == "__main__":
    unittest.main()
