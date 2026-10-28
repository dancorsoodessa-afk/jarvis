import io
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import stt, config


class TestSTT(unittest.TestCase):
    def setUp(self):
        self.old = {name: os.environ.get(name) for name in (
            "JARVIS_STT", "GEMINI_API_KEY", "JARVIS_CHAT_KEY", "JARVIS_STT_MODEL"
        )}
        os.environ["JARVIS_STT"] = "off"
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("JARVIS_CHAT_KEY", None)
        os.environ.pop("JARVIS_STT_MODEL", None)

    def tearDown(self):
        for name, value in self.old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_default_model_is_current_gemini_flash_lite(self):
        self.assertEqual(config.DEFAULT_MODEL, "gemini-3.5-flash-lite")
        self.assertEqual(stt.DEFAULT_STT_MODEL, "gemini-3.5-flash-lite")

    def test_off_raises(self):
        with self.assertRaises(RuntimeError):
            stt.transcribe("nonexistent.wav")

    def test_missing_file_raises_before_network(self):
        os.environ["JARVIS_STT"] = "gemini"
        os.environ["GEMINI_API_KEY"] = "test-key"
        with self.assertRaises(ValueError):
            stt.transcribe("no_such_file_123.wav")

    def test_cloud_engine_requires_key(self):
        self.assertEqual(stt.current_engine(), "off")
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["JARVIS_STT"] = "gemini"
        self.assertEqual(stt.current_engine(), "gemini")

    def test_transcribe_sends_audio_to_gemini(self):
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["JARVIS_STT"] = "gemini"

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return b'{"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}'

        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
                self.assertEqual(stt.transcribe(str(audio)), "hello")
                request = urlopen.call_args.args[0]
                self.assertIn("/gemini-3.5-flash-lite:generateContent", request.full_url)
                self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
                self.assertEqual(request.get_header("Content-type"), "application/json")
                self.assertIn("inline_data", request.data.decode("utf-8"))

    def test_stt_model_can_be_overridden(self):
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["JARVIS_STT"] = "gemini"
        os.environ["JARVIS_STT_MODEL"] = "gemini-custom-test"

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return b'{"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}'

        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
                stt.transcribe(str(audio))
                self.assertIn("/gemini-custom-test:generateContent", urlopen.call_args.args[0].full_url)

    def test_404_has_clear_model_error(self):
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["JARVIS_STT"] = "gemini"
        error = urllib.error.HTTPError("https://example.test", 404, "Not Found", {}, io.BytesIO(b"model not found"))
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, "не найдена"):
                    stt.transcribe(str(audio))

    def test_429_has_clear_quota_error_without_retry(self):
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["JARVIS_STT"] = "gemini"
        error = urllib.error.HTTPError("https://example.test", 429, "Quota exceeded", {}, io.BytesIO(b"quota exceeded"))
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", side_effect=error) as urlopen:
                with self.assertRaisesRegex(RuntimeError, "Исчерпана квота Gemini"):
                    stt.transcribe(str(audio))
                self.assertEqual(urlopen.call_count, 1)

    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        self.assertIn("transcribe", build_agent().tools.names())


if __name__ == "__main__":
    unittest.main()
