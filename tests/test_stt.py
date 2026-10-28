import io
import os
import urllib.error
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import stt


class TestSTT(unittest.TestCase):
    def setUp(self):
        self.old = {name: os.environ.get(name) for name in ("JARVIS_STT", "HF_TOKEN", "GEMINI_API_KEY", "JARVIS_CHAT_KEY", "JARVIS_STT_URL", "GROQ_API_KEY")}
        os.environ["JARVIS_STT"] = "off"
        os.environ.pop("HF_TOKEN", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("JARVIS_CHAT_KEY", None)
        os.environ.pop("GROQ_API_KEY", None)

    def tearDown(self):
        for name, value in self.old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_off_raises(self):
        with self.assertRaises(RuntimeError):
            stt.transcribe("nonexistent.wav")

    def test_missing_file_raises_before_network(self):
        os.environ["JARVIS_STT"] = "gemini"
        os.environ["GEMINI_API_KEY"] = "test-token"
        with self.assertRaises(ValueError):
            stt.transcribe("no_such_file_123.wav")

    def test_cloud_engine_requires_gemini_key(self):
        self.assertEqual(stt.current_engine(), "off")
        os.environ["GEMINI_API_KEY"] = "test-token"
        os.environ["JARVIS_STT"] = "gemini"
        self.assertEqual(stt.current_engine(), "gemini")

    def test_transcribe_posts_audio_to_gemini(self):
        os.environ["GEMINI_API_KEY"] = "test-token"
        os.environ["JARVIS_STT"] = "gemini"
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}'
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
                self.assertEqual(stt.transcribe(str(audio)), "hello")
                request = urlopen.call_args.args[0]
                self.assertTrue(request.full_url.startswith("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"))
                self.assertIn("key=test-token", request.full_url)

    def test_quota_exhaustion_uses_configured_groq_without_retrying_gemini(self):
        os.environ["JARVIS_STT"] = "auto"
        os.environ["GEMINI_API_KEY"] = "test-gemini"
        os.environ["GROQ_API_KEY"] = "test-groq"
        detail = b'{"error":{"message":"generate_content_free_tier_requests quota exceeded"}}'
        quota_error = urllib.error.HTTPError(
            "https://generativelanguage.googleapis.com", 429, "Too Many Requests", {}, io.BytesIO(detail)
        )
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch("urllib.request.urlopen", side_effect=quota_error) as urlopen, mock.patch.object(stt, "_transcribe_groq", return_value="резерв распознал речь") as groq:
                self.assertEqual(stt.transcribe(str(audio)), "резерв распознал речь")
                self.assertEqual(urlopen.call_count, 1, "Gemini quota exhaustion must not be retried")
                groq.assert_called_once()

    def test_timeout_uses_groq_when_configured(self):
        os.environ["JARVIS_STT"] = "auto"
        os.environ["GEMINI_API_KEY"] = "test-gemini"
        os.environ["GROQ_API_KEY"] = "test-groq"
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch.object(stt, "_transcribe_gemini", side_effect=RuntimeError("Тайм-аут Gemini STT")), mock.patch.object(stt, "_transcribe_groq", return_value="резервный текст") as groq:
                self.assertEqual(stt.transcribe(str(audio)), "резервный текст")
                groq.assert_called_once()

    def test_gemini_timeout_is_clear_without_reserve(self):
        os.environ["JARVIS_STT"] = "auto"
        os.environ["GEMINI_API_KEY"] = "test-gemini"
        os.environ.pop("GROQ_API_KEY", None)
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"RIFF-test")
            with mock.patch.object(stt, "_transcribe_gemini", side_effect=RuntimeError("Тайм-аут распознавания Gemini")) as gemini:
                with self.assertRaisesRegex(RuntimeError, "Тайм-аут"):
                    stt.transcribe(str(audio))
                gemini.assert_called_once()

    def test_groq_can_be_primary_if_only_groq_key_is_configured(self):
        os.environ["JARVIS_STT"] = "auto"
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ["GROQ_API_KEY"] = "test-groq"
        self.assertEqual(stt.current_engine(), "groq")

    def test_groq_multipart_transcription_request(self):
        os.environ["GROQ_API_KEY"] = "test-groq"
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"text":"transcribed text"}'
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "voice.wav"
            audio.write_bytes(b"RIFF-audio")
            with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
                self.assertEqual(stt._transcribe_groq(audio), "transcribed text")
            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, stt.GROQ_STT_URL)
            self.assertEqual(request.get_header("Authorization"), "Bearer test-groq")
            self.assertIn(b"whisper-large-v3-turbo", request.data)
            self.assertIn(b'name="language"\r\n\r\nru', request.data)
            self.assertIn(b"RIFF-audio", request.data)

    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        self.assertIn("transcribe", build_agent().tools.names())


if __name__ == "__main__":
    unittest.main()
