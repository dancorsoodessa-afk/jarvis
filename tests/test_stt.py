import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import stt


class TestSTT(unittest.TestCase):
    def setUp(self):
        self.old = {name: os.environ.get(name) for name in ("JARVIS_STT", "HF_TOKEN", "JARVIS_CHAT_KEY")}
        os.environ["JARVIS_STT"] = "off"
        os.environ.pop("HF_TOKEN", None)
        os.environ.pop("JARVIS_CHAT_KEY", None)

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
        os.environ["JARVIS_STT"] = "huggingface"
        os.environ["HF_TOKEN"] = "test-token"
        with self.assertRaises(ValueError):
            stt.transcribe("no_such_file_123.wav")

    def test_cloud_engine_requires_token(self):
        self.assertEqual(stt.current_engine(), "off")
        os.environ["HF_TOKEN"] = "test-token"
        os.environ["JARVIS_STT"] = "huggingface"
        self.assertEqual(stt.current_engine(), "huggingface")

    def test_transcribe_posts_audio_to_huggingface(self):
        os.environ["HF_TOKEN"] = "test-token"
        os.environ["JARVIS_STT"] = "huggingface"
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"text":"hello"}'
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            audio.write(b"RIFF-test")
            audio.flush()
            with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen:
                self.assertEqual(stt.transcribe(audio.name), "hello")
                request = urlopen.call_args.args[0]
                self.assertTrue(request.full_url.startswith("https://router.huggingface.co/"))
                self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        self.assertIn("transcribe", build_agent().tools.names())


if __name__ == "__main__":
    unittest.main()
