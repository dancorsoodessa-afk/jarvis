import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import stt

class TestSTT(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get("JARVIS_STT")
    def tearDown(self):
        if self.old is None:
            os.environ.pop("JARVIS_STT", None)
        else:
            os.environ["JARVIS_STT"] = self.old
    def test_off_raises(self):
        os.environ["JARVIS_STT"] = "off"
        with self.assertRaises(RuntimeError):
            stt.transcribe("nonexistent.wav")
    def test_missing_file_raises(self):
        os.environ["JARVIS_STT"] = "faster-whisper"
        with self.assertRaises(ValueError):
            stt.transcribe("no_such_file_123.wav")
    def test_only_faster_whisper_is_supported(self):
        self.assertIn(stt.current_engine(), {"faster-whisper", "off"})
    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        self.assertIn("transcribe", build_agent().tools.names())

if __name__ == "__main__":
    unittest.main()
