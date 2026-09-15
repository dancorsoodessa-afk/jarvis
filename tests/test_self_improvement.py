import tempfile
import unittest
from pathlib import Path

from agent.self_improvement import SelfImprovementManager


class TestSelfImprovement(unittest.TestCase):
    def test_full_controlled_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SelfImprovementManager(Path(tmp))
            proposal = manager.propose("ошибка", "исправление", ["pytest"])
            manager.mark_tested(proposal, {"passed": True})
            manager.request_confirmation(proposal)
            manager.confirm(proposal, True)
            manager.mark_verified(proposal, {"regression": False})
            manager.save(proposal)
            self.assertEqual(proposal.status, "saved")
            self.assertIn('"status": "saved"', manager.path.read_text(encoding="utf-8"))

    def test_cannot_skip_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SelfImprovementManager(tmp)
            proposal = manager.propose("ошибка", "исправление")
            manager.mark_tested(proposal, {"passed": True})
            with self.assertRaises(ValueError):
                manager.confirm(proposal, True)


if __name__ == "__main__":
    unittest.main()
