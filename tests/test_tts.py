import base64
import json
import os
import io
import urllib.error
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
    assert "language" not in payload["generation_config"]["speech_config"][0]
    assert "ru-RU" in payload["input"][0]["content"][0]["annotations"][0]["style"]


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



def test_tts_quota_error_is_not_retried(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    detail = b'{"error":{"message":"quota exceeded","status":"RESOURCE_EXHAUSTED"}}'
    error = urllib.error.HTTPError(
        tts.TTS_ENDPOINT, 429, "Too Many Requests", {}, io.BytesIO(detail)
    )
    with mock.patch("urllib.request.urlopen", side_effect=error) as urlopen:
        try:
            tts._generate_audio("Проверка")
        except RuntimeError as exc:
            assert "HTTP 429" in str(exc)
        else:
            raise AssertionError("Expected quota error")
    assert urlopen.call_count == 1
