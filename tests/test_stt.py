import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import stt


class TestSTT:
    def setup_method(self):
        self.old_quota_exceeded = stt.quota_exceeded()
        stt._set_quota_exceeded(False)
        self.old = {name: os.environ.get(name) for name in (
            "JARVIS_STT", "GEMINI_API_KEY", "JARVIS_CHAT_KEY", "GEMINI_MODEL", "JARVIS_STT_MODEL", "GEMINI_STT_MODEL", "GROQ_API_KEY", "JARVIS_STT_FALLBACK_MODEL"
        )}
        for name in ("JARVIS_STT", "GEMINI_API_KEY", "JARVIS_CHAT_KEY", "GEMINI_MODEL", "JARVIS_STT_MODEL", "GEMINI_STT_MODEL", "GROQ_API_KEY", "JARVIS_STT_FALLBACK_MODEL"):
            os.environ.pop(name, None)

    def teardown_method(self):
        for name, value in self.old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        stt._set_quota_exceeded(self.old_quota_exceeded)

    def test_cloud_gemini_is_default_when_key_exists(self):
        os.environ["GEMINI_API_KEY"] = "test-token"
        assert stt.current_engine() == "gemini"

    def test_no_key_fails_closed_instead_of_switching_provider(self):
        assert stt.current_engine() == "off"
        os.environ["GROQ_API_KEY"] = "legacy-key"
        assert stt.current_engine() == "off"

    def test_quota_exhaustion_does_not_fallback_to_local_automatically(self):
        os.environ["JARVIS_STT"] = "auto"
        os.environ["GEMINI_API_KEY"] = "test-token"
        stt._set_quota_exceeded(True)
        with mock.patch.object(stt, "_local_available", return_value=True):
            assert stt.current_engine() == "off"

    def test_explicit_local_mode_requires_local_whisper(self):
        os.environ["JARVIS_STT"] = "local"
        with mock.patch.object(stt, "_local_available", return_value=False):
            assert stt.current_engine() == "off"
        with mock.patch.object(stt, "_local_available", return_value=True):
            assert stt.current_engine() == "local"

    def test_missing_file_raises_before_network(self):
        os.environ["GEMINI_API_KEY"] = "test-token"
        with pytest.raises(ValueError, match="Файл не найден"):
            stt.transcribe("no_such_file_123.wav")

    def test_transcribe_posts_audio_to_gemini(self):
        os.environ["GEMINI_API_KEY"] = "test-token"

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return '{"candidates":[{"content":{"parts":[{"text":"открой браузер"}]}}]}'.encode("utf-8")

        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
                assert stt.transcribe(str(audio)) == "открой браузер"
            request = urlopen.call_args.args[0]
            assert request.full_url.startswith(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            )
            assert "key=test-token" in request.full_url
            payload = json.loads(request.data.decode("utf-8"))
            assert payload["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "audio/wav"

    def test_gemini_errors_are_reported_without_provider_fallback(self):
        os.environ["GEMINI_API_KEY"] = "test-token"
        detail = b'{"error":{"message":"quota exceeded"}}'
        error = urllib.error.HTTPError("https://generativelanguage.googleapis.com", 429, "Too Many Requests", {}, __import__("io").BytesIO(detail))
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", side_effect=error) as urlopen:
                with pytest.raises(RuntimeError, match="HTTP 429"):
                    stt.transcribe(str(audio))
                assert urlopen.call_count == 1

    def test_changing_gemini_key_clears_quota_degraded_state(self):
        os.environ["GEMINI_API_KEY"] = "old-key"
        stt._set_quota_exceeded(True)
        assert stt.quota_exceeded() is True
        os.environ["GEMINI_API_KEY"] = "new-key"
        assert stt.quota_exceeded() is False

    def test_groq_whisper_is_used_after_gemini_quota_exhaustion(self):
        os.environ["GEMINI_API_KEY"] = "gemini-test-token"
        os.environ["GROQ_API_KEY"] = "groq-test-token"
        detail = b'{"error":{"message":"quota exceeded","status":"RESOURCE_EXHAUSTED"}}'
        quota_error = urllib.error.HTTPError(
            "https://generativelanguage.googleapis.com", 429, "Too Many Requests", {},
            __import__("io").BytesIO(detail),
        )

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({"text": "открой настройки"}, ensure_ascii=False).encode("utf-8")

        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", side_effect=[quota_error, Response()]) as urlopen:
                assert stt.transcribe(str(audio)) == "открой настройки"
            assert urlopen.call_count == 2
            groq_request = urlopen.call_args.args[0]
            assert groq_request.full_url == stt.GROQ_STT_URL
            assert groq_request.get_header("Authorization") == "Bearer groq-test-token"
            assert b"whisper-large-v3-turbo" in groq_request.data
            assert b"RIFF-test" in groq_request.data
        assert stt.quota_exceeded()
        assert stt.current_engine() == "groq"

    def test_groq_quota_reserve_is_not_used_before_gemini_quota(self):
        os.environ["GEMINI_API_KEY"] = "gemini-test-token"
        os.environ["GROQ_API_KEY"] = "groq-test-token"
        assert stt.current_engine() == "gemini"

    def test_groq_code_is_present_as_configured_quota_fallback(self):
        source = (Path(__file__).resolve().parent.parent / "agent" / "stt.py").read_text(encoding="utf-8")
        assert "GROQ_API_KEY" in source
        assert "_transcribe_groq" in source

    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        assert "transcribe" in build_agent().tools.names()


import pytest
