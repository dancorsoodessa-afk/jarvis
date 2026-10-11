"""Regression tests for the audit fixes (rollback, endpoint, launch, UI widgets, tool-name clash)."""
import ast
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools import apps, self_modify
from agent.tools.registry import ConfirmationRequired, ToolRegistry


class TestRollback(unittest.TestCase):
    def test_rollback_restores_original_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pkg").mkdir()
            target = root / "pkg" / "mod.py"
            target.write_text("v1", encoding="utf-8")
            with mock.patch.object(self_modify, "ROOT", root), \
                 mock.patch.object(self_modify, "BACKUP_ROOT", root / ".jarvis_backups"):
                self_modify.write_source("pkg/mod.py", "v2")
                self.assertEqual(target.read_text(encoding="utf-8"), "v2")
                self_modify.rollback_last_backup()
                self.assertEqual(target.read_text(encoding="utf-8"), "v1")

    def test_rollback_without_backups_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(self_modify, "ROOT", root), \
                 mock.patch.object(self_modify, "BACKUP_ROOT", root / ".jarvis_backups"):
                with self.assertRaises(FileNotFoundError):
                    self_modify.rollback_last_backup()


class TestLaunchConfirmation(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry()
        self.calls = []
        self.reg.register("launch", lambda name="": self.calls.append(name) or "ok",
                          confirm_if=apps.launch_needs_confirmation)

    def test_bare_name_runs_without_confirmation(self):
        self.assertEqual(self.reg.call("launch", **{"name": "notepad"}), "ok")

    def test_paths_and_arguments_need_confirmation(self):
        for target in (r"C:\Users\me\Downloads\evil.exe", "script.bat",
                       "powershell -enc AAAA", "https://x.example/a.exe", "../x"):
            with self.subTest(target=target):
                with self.assertRaises(ConfirmationRequired):
                    self.reg.call("launch", **{"name": target})
        self.assertEqual(self.calls, [])

    def test_confirmed_call_runs(self):
        self.assertEqual(self.reg.call("launch", **{"name": "a.exe"}, _confirmed=True), "ok")


class TestLlmToolCallWithNameParam(unittest.TestCase):
    def test_tools_with_name_parameter_do_not_crash(self):
        """launch/ps have a 'name' argument that used to clash with the tool name."""
        from agent.runtime import build_agent
        agent = build_agent()
        out = agent._execute_for_llm("launch", {"name": r"C:\\x\\evil.exe"})
        self.assertIn("подтверждения", out)
        self.assertIsInstance(agent._execute_for_llm("ps", {"name": "python"}), str)


class TestReactorStarts(unittest.TestCase):
    def test_orb_animation_is_started_in_init(self):
        """_draw_orb reschedules itself but was never called, so the 3D reactor stayed blank."""
        src = (Path(__file__).resolve().parent.parent / "jarvis_desktop.py").read_text(encoding="utf-8")
        init = src.split("def __init__", 1)[1].split("\n    def ", 1)[0]
        self.assertRegex(init, r"self\.after\([^)]*self\._draw_orb")


class TestSafeEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import jarvis_desktop
        except ImportError as exc:  # tkinter missing
            raise unittest.SkipTest(str(exc))
        cls.jd = jarvis_desktop

    def test_empty_gives_default(self):
        self.assertEqual(self.jd._safe_endpoint(""), self.jd.DEFAULT_URL)

    def test_remote_url_kept(self):
        url = "https://api.example.com/v1/chat/completions"
        self.assertEqual(self.jd._safe_endpoint(url), url)

    def test_dead_local_endpoint_falls_back(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.assertEqual(self.jd._safe_endpoint(f"http://127.0.0.1:{port}/v1"), self.jd.DEFAULT_URL)

    def test_running_local_endpoint_is_kept(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            url = f"http://localhost:{s.getsockname()[1]}/v1/chat/completions"
            self.assertEqual(self.jd._safe_endpoint(url), url)


class TestDesktopWidgets(unittest.TestCase):
    def test_every_self_attribute_is_defined(self):
        """jarvis_desktop used tools_button/enabled_label/side_core/side_voice without creating them."""
        try:
            import tkinter
        except ImportError as exc:
            self.skipTest(str(exc))
        src = (Path(__file__).resolve().parent.parent / "jarvis_desktop.py").read_text(encoding="utf-8")
        cls = next(n for n in ast.parse(src).body
                   if isinstance(n, ast.ClassDef) and n.name == "JarvisDesktop")
        methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        assigned, used = set(), {}
        for n in ast.walk(cls):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self":
                if isinstance(n.ctx, ast.Store):
                    assigned.add(n.attr)
                else:
                    used.setdefault(n.attr, n.lineno)
        missing = {a: l for a, l in used.items()
                   if a not in assigned and a not in methods and not hasattr(tkinter.Tk, a)}
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
