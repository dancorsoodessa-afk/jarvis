import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.logging_setup import setup, get


class TestLoggingSetup(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_file = Path(self._tmp.name) / "test_jarvis.log"
        self._env_backup = {k: os.environ.get(k) for k in
                            ("JARVIS_LOG", "JARVIS_LOG_LEVEL", "JARVIS_MEMORY")}
        os.environ["JARVIS_LOG"] = str(self.log_file)

    def tearDown(self):
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _fresh_logger(self):
        logger = logging.getLogger("jarvis")
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger._jarvis_configured = False
        self.addCleanup(lambda: [logger.removeHandler(h) for h in list(logger.handlers)])
        return logger

    def test_writes_to_rotating_file(self):
        self._fresh_logger()
        log = get("test")
        log.info("проверка записи")
        for h in logging.getLogger("jarvis").handlers:
            h.flush()
        content = self.log_file.read_text(encoding="utf-8")
        self.assertIn("проверка записи", content)
        self.assertIn("test", content)

    def test_idempotent_no_duplicate_handlers(self):
        self._fresh_logger()
        setup()
        n = len(logging.getLogger("jarvis").handlers)
        setup()
        self.assertEqual(len(logging.getLogger("jarvis").handlers), n)

    def test_level_respected(self):
        self._fresh_logger()
        os.environ["JARVIS_LOG_LEVEL"] = "WARNING"
        log = get("test")
        log.info("не должно попасть")
        for h in logging.getLogger("jarvis").handlers:
            h.flush()
        content = self.log_file.read_text(encoding="utf-8")
        self.assertNotIn("не должно попасть", content)

    def test_bad_log_path_does_not_crash(self):
        self._fresh_logger()
        os.environ["JARVIS_LOG"] = "/proc/definitely/not/writable/x.log"
        log = get("test")  # must not raise
        log.info("still alive")


if __name__ == "__main__":
    unittest.main()
