import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import stt, tts


class TestVoiceStackRegressions(unittest.TestCase):
    def test_stt_disables_internal_vad_when_recorder_already_segments_audio(self):
        calls = {}

        class FakeModel:
            def transcribe(self, *args, **kwargs):
                calls["kwargs"] = kwargs
                return ([], None)

        fake_fw = types.SimpleNamespace(WhisperModel=lambda *a, **k: FakeModel())
        old_model = stt._MODEL
        stt._MODEL = None
        try:
            with mock.patch.dict(sys.modules, {"faster_whisper": fake_fw}):
                with mock.patch.dict(os.environ, {"JARVIS_STT": "faster-whisper"}):
                    with mock.patch.object(stt, "_model_dir", return_value=Path("/missing")):
                        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
                            stt.transcribe(audio.name)
        finally:
            stt._MODEL = old_model
        self.assertIs(calls["kwargs"]["vad_filter"], False)

    def test_piper_creates_unique_output_paths(self):
        with mock.patch.object(tts, "_piper_paths", return_value=("piper.exe", Path("voice.onnx"))):
            with mock.patch("subprocess.run"):
                with mock.patch("tempfile.mkstemp", side_effect=[
                    (1, str(Path(os.getenv("TEMP", "/tmp")) / "jarvis_a.wav")),
                    (2, str(Path(os.getenv("TEMP", "/tmp")) / "jarvis_b.wav")),
                ]):
                    first = tts._speak_piper("первый")
                    second = tts._speak_piper("второй")
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
