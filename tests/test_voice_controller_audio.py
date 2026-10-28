import wave
import io

import numpy as np

from agent.voice_controller import _resample_pcm16, _supported_capture_rate


class FakeSoundDevice:
    def check_input_settings(self, *, device, samplerate, channels, dtype):
        if samplerate != 48000:
            raise ValueError("unsupported samplerate")

    def query_devices(self, device, kind):
        assert kind == "input"
        return {"default_samplerate": 48000}


def test_capture_rate_falls_back_to_input_device_default():
    assert _supported_capture_rate(FakeSoundDevice(), None, 16000) == 48000


def test_resample_pcm16_preserves_signal_and_duration():
    frames = [np.full(4800, 12000, dtype=np.int16).tobytes()]
    result = np.frombuffer(_resample_pcm16(frames, 48000, 16000), dtype=np.int16)
    assert result.dtype == np.int16
    assert result.size == 1600
    assert abs(int(result.mean()) - 12000) <= 1


def test_capture_wav_is_written_at_stt_sample_rate():
    frames = [np.full(4800, 1000, dtype=np.int16).tobytes()]
    from agent.voice_controller import AudioCapture
    wav_bytes = AudioCapture._wav(frames, 48000)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        assert wav.getframerate() == 16000
        assert wav.getnframes() == 1600
