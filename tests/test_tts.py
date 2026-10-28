import base64
import json
import os
from unittest import mock

from agent import tts


def test_legacy_dmitri_voice_is_normalized_to_gemini_profile(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_TTS_VOICE", "Dmitri Medium")
    audio = base64.b64encode(b"pcm-test").decode("ascii")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"output_audio": {"data": audio}}).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
        assert tts._generate_audio("Проверка") == b"pcm-test"

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["generation_config"]["speech_config"][0]["voice"] == "Charon"


def test_unknown_tts_voice_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_TTS_VOICE", "Not A Gemini Voice")
    audio = base64.b64encode(b"pcm-test").decode("ascii")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"output_audio": {"data": audio}}).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
        assert tts._generate_audio("Проверка") == b"pcm-test"

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert payload["generation_config"]["speech_config"][0]["voice"] == tts.DEFAULT_TTS_VOICE
