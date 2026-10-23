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

    def test_tts_auto_uses_gemini_when_key_is_configured(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}):
            with mock.patch.object(tts, "_api_key", return_value="test-key"):
                self.assertEqual(tts.current_engine(), "gemini")

    def test_tts_auto_is_off_without_gemini_key(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "auto"}):
            with mock.patch.object(tts, "_api_key", return_value=""):
                self.assertEqual(tts.current_engine(), "off")

    def test_tts_uses_rest_input_schema_and_reads_audio_from_steps(self):
        audio = b"RIFF-test-wav-data"
        encoded = base64.b64encode(audio).decode("ascii")
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "steps": [{
                "type": "model_output",
                "content": [{"type": "audio", "data": encoded}],
            }]
        }).encode("utf-8")

        with mock.patch.object(tts, "_api_key", return_value="test-key"):
            with mock.patch.object(tts.urllib.request, "urlopen", return_value=response) as urlopen:
                result = tts._generate_audio("Привет, Джарвис")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        text_block = payload["input"][0]["content"][0]
        self.assertEqual(text_block["text"], "Привет, Джарвис")
        self.assertEqual(text_block["annotations"][0]["type"], "speech_metadata")
        self.assertEqual(payload["response_format"], {"type": "audio"})
        self.assertEqual(result, audio)

    def test_tts_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "off"}):
            self.assertEqual(tts.current_engine(), "off")

    def test_tts_rejects_unknown_engine(self):
        with mock.patch.dict(os.environ, {"JARVIS_TTS": "unknown"}):
            with self.assertRaisesRegex(RuntimeError, "облачную озвучку Gemini"):
                tts.current_engine()


if __name__ == "__main__":
    unittest.main()
