import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agent.secrets import protect_secret, unprotect_secret


class TestSecrets(unittest.TestCase):
    def test_roundtrip(self):
        value = "jarvis-secret-123"
        protected = protect_secret(value)
        self.assertTrue(protected)
        self.assertEqual(unprotect_secret(protected), value)

    def test_empty_secret_stays_empty(self):
        self.assertEqual(protect_secret(""), "")
        self.assertEqual(unprotect_secret(""), "")


if __name__ == "__main__":
    unittest.main()
