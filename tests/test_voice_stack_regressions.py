import os
import unittest
from unittest import mock

from agent import stt, tts


class TestCloudVoiceRegressions(unittest.TestCase):
    def test_stt_does_not_load_local_whisper(self):
        with mock.patch.dict(os.environ, {"JARVIS_STT": "off"}):
            self.assertEqual(stt.current_engine(), "off")

    def test_stt_does_not_accept_huggingface_token_as_groq_key(self):
        with mock.patch.dict(os.environ, {"JARVIS_STT": "auto", "HF_TOKEN": "old-token"}, clear=True):
            self.assertEqual(stt.current_engine(), "off")

    def test_tts_auto_has_free_windows_fallback(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}):
            with mock.patch.object(tts.sys, "platform", "win32"):
                self.assertEqual(tts.current_engine(), "windows")

    def test_tts_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "off"}):
            self.assertEqual(tts.current_engine(), "off")

    def test_tts_rejects_unknown_engine(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "unknown"}):
            with self.assertRaisesRegex(RuntimeError, "Выберите системную озвучку"):
                tts.current_engine()


if __name__ == "__main__":
    unittest.main()
