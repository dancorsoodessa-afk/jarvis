import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.tools import self_modify


class TestSelfModifyBackups(unittest.TestCase):
    def test_write_source_backup_restores_nested_path_with_underscores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "agent" / "tools" / "my_module_name.py"
            target.parent.mkdir(parents=True)
            target.write_text("original = True\n", encoding="utf-8")
            backups = root / ".jarvis_backups"
            with mock.patch.object(self_modify, "ROOT", root), mock.patch.object(self_modify, "BACKUP_ROOT", backups):
                self_modify.write_source("agent/tools/my_module_name.py", "changed = True\n")
                self.assertEqual(target.read_text(encoding="utf-8"), "changed = True\n")
                result = self_modify.rollback_last_backup()
            self.assertIn("agent/tools/my_module_name.py", result)
            self.assertEqual(target.read_text(encoding="utf-8"), "original = True\n")

    def test_rollback_ignores_empty_backup_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backups = root / ".jarvis_backups"
            (backups / "20261107_120000_000001").mkdir(parents=True)
            with mock.patch.object(self_modify, "ROOT", root), mock.patch.object(self_modify, "BACKUP_ROOT", backups):
                with self.assertRaises(FileNotFoundError):
                    self_modify.rollback_last_backup()

    def test_rollback_removes_file_created_by_self_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "agent" / "new_module.py"
            backups = root / ".jarvis_backups"
            with mock.patch.object(self_modify, "ROOT", root), mock.patch.object(self_modify, "BACKUP_ROOT", backups):
                self_modify.write_source("agent/new_module.py", "created = True\n")
                self.assertTrue(target.is_file())
                result = self_modify.rollback_last_backup()
            self.assertIn("Удалён новый файл", result)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
