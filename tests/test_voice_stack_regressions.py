import os
import unittest
from unittest import mock

from agent import stt, tts


class TestCloudVoiceRegressions(unittest.TestCase):
    def test_stt_does_not_load_local_whisper(self):
        with mock.patch.dict(os.environ, {"JARVIS_STT": "off"}):
            self.assertEqual(stt.current_engine(), "off")

    def test_stt_requires_gemini_key_not_huggingface(self):
        with mock.patch.dict(os.environ, {"JARVIS_STT": "auto", "HF_TOKEN": "old-token"}, clear=False):
            with mock.patch.object(stt, "_token", return_value=""):
                self.assertEqual(stt.current_engine(), "off")

    def test_tts_auto_uses_gemini_when_key_is_configured(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}):
            with mock.patch.object(tts, "_api_key", return_value="test-key"):
                self.assertEqual(tts.current_engine(), "gemini")

    def test_tts_auto_is_off_without_gemini_key(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}):
            with mock.patch.object(tts, "_api_key", return_value=""):
                self.assertEqual(tts.current_engine(), "off")

    def test_tts_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "off"}):
            self.assertEqual(tts.current_engine(), "off")

    def test_tts_rejects_unknown_engine(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "unknown"}):
            with self.assertRaisesRegex(RuntimeError, "облачную озвучку Gemini"):
                tts.current_engine()


if __name__ == "__main__":
    unittest.main()
