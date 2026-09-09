import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.skills import NoteStore, calculate, now


class TestNotes(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        from pathlib import Path
        self.store = NoteStore(Path(self._tmp.name) / "notes.json")

    def test_add_and_recall(self):
        self.store.add("Пароль от роутера: 1234", tags="пароли роутер")
        self.store.add("Мама родилась в 1965")
        out = self.store.recall("роутер")
        self.assertIn("1234", out)
        self.assertIn("пароли", out)
        self.assertNotIn("1965", out)

    def test_recall_all_and_empty(self):
        self.assertEqual(self.store.recall(), "Заметок пока нет.")
        self.store.add("заметка раз")
        self.store.add("заметка два")
        out = self.store.recall()
        self.assertIn("#1", out)
        self.assertIn("#2", out)

    def test_no_match(self):
        self.store.add("что-то")
        self.assertEqual(self.store.recall("несуществующее"), "Ничего не нашлось по запросу.")

    def test_forget(self):
        self.store.add("запомнить это")
        out = self.store.forget(1)
        self.assertIn("Забыл", out)
        self.assertEqual(self.store.recall(), "Заметок пока нет.")
        self.assertIn("не найдена", self.store.forget(99))

    def test_empty_note_raises(self):
        with self.assertRaises(ValueError):
            self.store.add("   ")

    def test_persists_between_instances(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "n.json"
            NoteStore(path).add("долговременный факт")
            self.assertIn("долговременный факт", NoteStore(path).recall())


class TestCalculator(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(calculate("2 + 2"), "2 + 2 = 4")
        self.assertEqual(calculate("(2+3)*7"), "(2+3)*7 = 35")
        self.assertEqual(calculate("10 / 4"), "10 / 4 = 2.5")
        self.assertEqual(calculate("2 ** 10"), "2 ** 10 = 1024")
        self.assertEqual(calculate("7 // 2"), "7 // 2 = 3")
        self.assertEqual(calculate("10 % 3"), "10 % 3 = 1")

    def test_russian_x_and_comma(self):
        self.assertEqual(calculate("2 х 3"), "2 х 3 = 6")
        self.assertEqual(calculate("2,5 + 0,5"), "2,5 + 0,5 = 3")

    def test_rejects_code(self):
        for bad in ("__import__('os')", "1 if 2 else 3", "'a'+'b'", ""):
            with self.assertRaises(ValueError):
                calculate(bad)


class TestNow(unittest.TestCase):
    def test_format(self):
        out = now()
        self.assertIn("Сейчас", out)
        self.assertIn("года", out)


class TestSkillsRegistered(unittest.TestCase):
    def test_in_runtime(self):
        from agent.runtime import build_agent
        agent = build_agent()
        for name in ("remember", "recall", "forget", "calc", "now"):
            self.assertIn(name, agent.tools.names())


if __name__ == "__main__":
    unittest.main()
