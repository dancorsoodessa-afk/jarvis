import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools import apps, audio, files


class TestFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        (root / "notes.txt").write_text("hi", encoding="utf-8")
        (root / "sub").mkdir()
        (root / "sub" / "photo.png").write_bytes(b"\x89PNG")

    def test_search_finds_matching_files(self):
        found = files.search("*.txt", self.dir.name)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].endswith("notes.txt"))

    def test_search_is_case_insensitive_and_recursive(self):
        found = files.search("*.PNG", self.dir.name)
        self.assertEqual(len(found), 1)

    def test_search_rejects_bad_root(self):
        with self.assertRaises(ValueError):
            files.search("*.txt", "/no/such/dir/xyz")

    def test_delete_removes_file(self):
        target = Path(self.dir.name) / "notes.txt"
        self.assertIn("Deleted", files.delete(str(target)))
        self.assertFalse(target.exists())

    def test_delete_rejects_directory(self):
        with self.assertRaises(ValueError):
            files.delete(self.dir.name)


class TestApps(unittest.TestCase):
    def test_launch_rejects_empty_command(self):
        with self.assertRaises(ValueError):
            apps.launch("   ")

    def test_launch_unknown_binary_raises(self):
        if sys.platform == "win32":
            self.skipTest("posix-only check")
        with self.assertRaises(FileNotFoundError):
            apps.launch("definitely-not-a-real-binary-xyz123")


class TestAudio(unittest.TestCase):
    def test_set_volume_validates_range(self):
        with self.assertRaises(ValueError):
            audio.set_volume("150")
        with self.assertRaises(ValueError):
            audio.set_volume("-5")


if __name__ == "__main__":
    unittest.main()
