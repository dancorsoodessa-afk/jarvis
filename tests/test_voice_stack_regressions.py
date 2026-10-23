import os
import unittest
from unittest import mock

from agent import stt, tts


class TestCloudVoiceRegressions(unittest.TestCase):
    def test_stt_does_not_load_local_whisper(self):
        with mock.patch.dict(os.environ, {"JARVIS_STT": "off"}):
            self.assertEqual(stt.current_engine(), "off")

    def test_tts_is_disabled_without_cloud_credentials(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}, clear=False):
            with mock.patch.object(tts, "_eleven_key", return_value=""):
                self.assertEqual(tts.current_engine(), "off")

    def test_tts_rejects_local_engine(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "piper"}):
            with self.assertRaisesRegex(RuntimeError, "только облачный TTS"):
                tts.current_engine()


if __name__ == "__main__":
    unittest.main()
