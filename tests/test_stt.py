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
        self.old = {name: os.environ.get(name) for name in (
            "JARVIS_STT", "GEMINI_API_KEY", "JARVIS_CHAT_KEY", "JARVIS_STT_MODEL", "GROQ_API_KEY"
        )}
        for name in ("JARVIS_STT", "GEMINI_API_KEY", "JARVIS_CHAT_KEY", "JARVIS_STT_MODEL", "GROQ_API_KEY"):
            os.environ.pop(name, None)

    def teardown_method(self):
        for name, value in self.old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_cloud_gemini_is_default_when_key_exists(self):
        os.environ["GEMINI_API_KEY"] = "test-token"
        assert stt.current_engine() == "gemini"

    def test_no_key_fails_closed_instead_of_switching_provider(self):
        assert stt.current_engine() == "off"
        os.environ["GROQ_API_KEY"] = "legacy-key"
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
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
            )
            assert "key=test-token" in request.full_url
            payload = json.loads(request.data.decode("utf-8"))
            assert payload["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "audio/wav"

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

    def test_no_groq_code_remains_in_stt_module(self):
        source = (Path(__file__).resolve().parent.parent / "agent" / "stt.py").read_text(encoding="utf-8")
        assert "GROQ_API_KEY" not in source
        assert "_transcribe_groq" not in source

    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        assert "transcribe" in build_agent().tools.names()


import pytest
