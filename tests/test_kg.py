import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.memory.graph import KnowledgeGraph
from agent.runtime import build_agent
from agent.config import Settings


class TestKnowledgeGraph(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.kg_file = Path(self._tmp.name) / "test_kg.json"
        self.kg = KnowledgeGraph(self.kg_file)

    def test_empty_graph(self):
        self.assertIn("пуст", self.kg.query("любое"))
        self.assertIn("пуст", self.kg.visualize())
        self.assertIn("пуст", self.kg.stats())

    def test_add_fact_and_query(self):
        msg = self.kg.add_fact("Алексей", "разработчик", "Jarvis")
        self.assertIn("Запомнил факт", msg)

        # Query by source
        q_src = self.kg.query("Алексей")
        self.assertIn("Алексей", q_src)
        self.assertIn("разработчик", q_src)
        self.assertIn("Jarvis", q_src)

        # Query by target
        q_tgt = self.kg.query("Jarvis")
        self.assertIn("Jarvis", q_tgt)
        self.assertIn("Алексей", q_tgt)

        # Query by relation
        q_rel = self.kg.query("разработчик")
        self.assertIn("Алексей", q_rel)
        self.assertIn("Jarvis", q_rel)

    def test_add_fact_semicolon_format(self):
        msg = self.kg.add_fact("Сервер ; ip адрес ; 192.168.1.10")
        self.assertIn("Запомнил факт", msg)
        q = self.kg.query("Сервер")
        self.assertIn("192.168.1.10", q)

    def test_add_fact_duplicate(self):
        self.kg.add_fact("Алексей", "друг", "Иван")
        msg = self.kg.add_fact("Алексей", "друг", "Иван")
        self.assertIn("уже известен", msg)

        data = self.kg._load()
        self.assertEqual(len(data["relations"]), 1)

    def test_entity_types(self):
        self.kg.add_fact("Алексей", "любит", "Python", source_type="человек", target_type="язык")
        q = self.kg.query("Алексей")
        self.assertIn("[человек]", q)
        q_py = self.kg.query("Python")
        self.assertIn("[язык]", q_py)

    def test_empty_args_raises(self):
        with self.assertRaises(ValueError):
            self.kg.add_fact("", "связь", "цель")
        with self.assertRaises(ValueError):
            self.kg.add_fact("субъект", "  ", "цель")
        with self.assertRaises(ValueError):
            self.kg.add_fact("субъект", "связь", "")

    def test_remove_fact(self):
        self.kg.add_fact("Алексей", "работает в", "Компании")
        self.assertIn("работает в", self.kg.query("Алексей"))

        msg = self.kg.remove_fact("Алексей", "работает в", "Компании")
        self.assertIn("Удалена связь", msg)
        self.assertNotIn("работает в", self.kg.query("Алексей"))

        # Non-existent fact
        msg2 = self.kg.remove_fact("Алексей", "работает в", "Компании")
        self.assertIn("не найдена", msg2)

    def test_remove_entity(self):
        self.kg.add_fact("Алексей", "друг", "Иван")
        self.kg.add_fact("Иван", "знает", "Python")

        msg = self.kg.remove_entity("Иван")
        self.assertIn("удалена", msg)

        # Relations connected to Иван must be deleted
        data = self.kg._load()
        self.assertEqual(len(data["relations"]), 0)
        self.assertNotIn("иван", data["entities"])

    def test_delete_convenience(self):
        self.kg.add_fact("А", "связан с", "Б")
        # Delete via triple
        self.kg.delete("А ; связан с ; Б")
        self.assertEqual(len(self.kg._load()["relations"]), 0)

        # Delete entity
        self.kg.add_fact("В", "связан с", "Г")
        self.kg.delete("В")
        self.assertNotIn("в", self.kg._load()["entities"])

        with self.assertRaises(ValueError):
            self.kg.delete("   ")

    def test_find_path(self):
        self.kg.add_fact("Иван", "друг", "Алексей")
        self.kg.add_fact("Алексей", "создал", "Jarvis")
        self.kg.add_fact("Jarvis", "написан на", "Python")

        path = self.kg.find_path("Иван", "Python")
        self.assertIn("Путь связей", path)
        self.assertIn("Иван", path)
        self.assertIn("Алексей", path)
        self.assertIn("Jarvis", path)
        self.assertIn("Python", path)

        # Same entity
        self.assertIn("одна и та же сущность", self.kg.find_path("Иван", "Иван"))

        # No connection
        self.kg.add_fact("Марс", "планета", "Солнечной системы")
        no_path = self.kg.find_path("Иван", "Марс")
        self.assertIn("не найдена", no_path)

    def test_visualize(self):
        self.kg.add_fact("Пользователь", "использует", "Jarvis")
        chart = self.kg.visualize()
        self.assertIn("```mermaid", chart)
        self.assertIn("graph TD", chart)
        self.assertIn("Пользователь", chart)
        self.assertIn("Jarvis", chart)
        self.assertIn("использует", chart)

        # Subgraph focus
        sub = self.kg.visualize("Jarvis")
        self.assertIn("подграф для", sub)

    def test_stats(self):
        self.kg.add_fact("А", "к", "Б")
        self.kg.add_fact("А", "к", "В")
        st = self.kg.stats()
        self.assertIn("Сущностей: 3", st)
        self.assertIn("Связей (фактов): 2", st)
        self.assertIn("А (2)", st)

    def test_persistence_and_atomic_save(self):
        self.kg.add_fact("Память", "тип", "Долговременная")
        new_instance = KnowledgeGraph(self.kg_file)
        q = new_instance.query("Память")
        self.assertIn("Долговременная", q)

    def test_corrupted_file_recovery(self):
        self.kg_file.write_text("NOT_JSON", encoding="utf-8")
        recovered_kg = KnowledgeGraph(self.kg_file)
        data = recovered_kg._load()
        self.assertEqual(data, {"entities": {}, "relations": []})


class TestKGIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mem_file = Path(self._tmp.name) / "memory.json"
        self.kg_file = Path(self._tmp.name) / "kg.json"
        self.settings = Settings(
            memory_path=str(self.mem_file),
            kg_path=str(self.kg_file),
        )

    def test_tools_registered(self):
        agent = build_agent(self.settings)
        for name in ("kg_add", "kg_query", "kg_relate", "kg_forget", "kg_show"):
            self.assertIn(name, agent.tools.names())

    def test_slash_commands(self):
        agent = build_agent(self.settings)

        # /kg_add
        res_add = agent.handle("/kg_add Дмитрий разработчик Jarvis")
        self.assertEqual(res_add.tool_used, "kg_add")
        self.assertIn("Запомнил факт", res_add.text)

        # /kg_query
        res_q = agent.handle("/kg_query Дмитрий")
        self.assertEqual(res_q.tool_used, "kg_query")
        self.assertIn("Jarvis", res_q.text)

        # /kg_show
        res_s = agent.handle("/kg_show")
        self.assertEqual(res_s.tool_used, "kg_show")
        self.assertIn("mermaid", res_s.text)

    def test_quoted_slash_commands(self):
        agent = build_agent(self.settings)

        res = agent.handle('/kg_add "Иван Иванов" "любит пить" "зелёный чай"')
        self.assertEqual(res.tool_used, "kg_add")
        self.assertIn("Иван Иванов", res.text)
        self.assertIn("зелёный чай", res.text)

        res_q = agent.handle('/kg_query "Иван Иванов"')
        self.assertIn("зелёный чай", res_q.text)


if __name__ == "__main__":
    unittest.main()

