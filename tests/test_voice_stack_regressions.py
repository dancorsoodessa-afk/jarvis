import base64
import json
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

    def test_tts_stays_off_even_when_api_key_is_configured(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}):
            with mock.patch.object(tts, "_api_key", return_value="test-key"):
                self.assertEqual(tts.current_engine(), "off")

    def test_tts_auto_is_off_without_gemini_key(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}):
            with mock.patch.object(tts, "_api_key", return_value=""):
                self.assertEqual(tts.current_engine(), "off")

    def test_tts_api_generation_is_disabled(self):
        with self.assertRaisesRegex(RuntimeError, "Озвучка через Gemini API отключена"):
            tts._generate_audio("Привет, Джарвис")

    def test_raw_gemini_pcm_is_wrapped_in_wav(self):
        import wave
        import tempfile
        from pathlib import Path
        pcm = b"\x00\x00" * 120
        path = tts._write_audio(pcm)
        try:
            with wave.open(str(path), "rb") as audio_file:
                self.assertEqual(audio_file.getframerate(), 24000)
                self.assertEqual(audio_file.getnchannels(), 1)
                self.assertEqual(audio_file.getsampwidth(), 2)
                self.assertEqual(audio_file.readframes(audio_file.getnframes()), pcm)
        finally:
            path.unlink(missing_ok=True)

    def test_tts_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "off"}):
            self.assertEqual(tts.current_engine(), "off")

    def test_tts_api_is_always_off_in_web_only_mode(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "unknown"}):
            self.assertEqual(tts.current_engine(), "off")


if __name__ == "__main__":
    unittest.main()
