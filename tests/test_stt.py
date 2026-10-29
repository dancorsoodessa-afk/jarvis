import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import stt


class TestSTT(unittest.TestCase):
    def setUp(self):
        self.old = {name: os.environ.get(name) for name in ("JARVIS_STT", "HF_TOKEN", "GEMINI_API_KEY", "JARVIS_CHAT_KEY", "JARVIS_STT_URL")}
        os.environ["JARVIS_STT"] = "off"
        os.environ.pop("HF_TOKEN", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("JARVIS_CHAT_KEY", None)

    def tearDown(self):
        for name, value in self.old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_off_raises(self):
        with self.assertRaises(RuntimeError):
            stt.transcribe("nonexistent.wav")

    def test_transcription_is_disabled_even_with_api_key(self):
        os.environ["GEMINI_API_KEY"] = "test-token"
        with self.assertRaisesRegex(RuntimeError, "используйте микрофон в Gemini Web"):
            stt.transcribe("no_such_file_123.wav")

    def test_cloud_engine_requires_gemini_key(self):
        self.assertEqual(stt.current_engine(), "off")
        os.environ["GEMINI_API_KEY"] = "test-token"
        os.environ["JARVIS_STT"] = "gemini"
        self.assertEqual(stt.current_engine(), "off")

    def test_transcribe_is_disabled_in_gemini_web_only_mode(self):
        os.environ["GEMINI_API_KEY"] = "test-token"
        with self.assertRaisesRegex(RuntimeError, "используйте микрофон в Gemini Web"):
            stt.transcribe("sample.wav")

    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        self.assertIn("transcribe", build_agent().tools.names())


if __name__ == "__main__":
    unittest.main()
