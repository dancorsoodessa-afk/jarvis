import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import stt


class TestSTT(unittest.TestCase):
    def setUp(self):
        self._env_backup = {k: os.environ.get(k) for k in
                            ("JARVIS_STT", "JARVIS_WHISPER", "JARVIS_WHISPER_MODEL")}

    def tearDown(self):
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_off_by_default_raises(self):
        os.environ["JARVIS_STT"] = "off"
        with self.assertRaises(RuntimeError):
            stt.transcribe("nonexistent.wav")

    def test_missing_file_raises(self):
        os.environ["JARVIS_STT"] = "faster-whisper"
        with self.assertRaises(ValueError):
            stt.transcribe("no_such_file_123.wav")

    def test_whisper_cpp_requires_paths(self):
        import tempfile
        os.environ["JARVIS_STT"] = "whisper-cpp"
        os.environ["JARVIS_WHISPER"] = "no_such_exe"
        with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
            with self.assertRaises(RuntimeError):
                stt.transcribe(wav.name)

    def test_whisper_cpp_run(self):
        import tempfile
        os.environ["JARVIS_STT"] = "whisper-cpp"
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "fake_whisper"
            exe.write_text("#!/bin/sh\necho 'привет мир'\n")
            exe.chmod(0o755)
            model = Path(d) / "fake_model.bin"
            model.write_text("x")
            wav = Path(d) / "fake.wav"
            wav.write_bytes(b"RIFF")
            os.environ["JARVIS_WHISPER"] = str(exe)
            os.environ["JARVIS_WHISPER_MODEL"] = str(model)
            self.assertEqual(stt.transcribe(str(wav)), "привет мир")

    def test_transcribe_tool_registered(self):
        from agent.runtime import build_agent
        agent = build_agent()
        self.assertIn("transcribe", agent.tools.names())


if __name__ == "__main__":
    unittest.main()
