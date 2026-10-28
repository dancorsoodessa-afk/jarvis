import numpy as np

from agent import voice
from agent.core import JarvisAgent
from agent.tools.registry import ToolRegistry
from agent.voice_loop import VoiceLoop


class FakeSoundDevice:
    def check_input_settings(self, *, device, samplerate, channels, dtype):
        if samplerate != 48000:
            raise ValueError("sample rate unsupported")

    def query_devices(self, device, kind):
        assert kind == "input"
        return {"default_samplerate": 48000}


def test_capture_rate_falls_back_to_device_default():
    assert voice._supported_capture_rate(FakeSoundDevice(), 16000, None) == 48000


def test_resample_returns_target_duration_and_int16():
    frames = [np.full(4800, 12000, dtype=np.int16)]
    converted = voice._resample_frames(frames, 48000, 16000)
    assert len(converted) == 1
    assert converted[0].dtype == np.int16
    assert len(converted[0]) == 1600
    assert abs(int(converted[0].mean()) - 12000) <= 1


class FakeProvider:
    name = "test-provider"

    def generate(self, prompt, **kwargs):
        return "unused"


def test_wake_word_to_registered_tool_round_trip():
    registry = ToolRegistry()
    registry.register("echo", lambda text: f"tool-result:{text}")
    agent = JarvisAgent(FakeProvider(), tools=registry)
    loop = VoiceLoop(agent, wake_enabled=True, wake_words=("jarvis",))

    result = loop.step("Jarvis /echo hello from microphone")

    assert result == "tool-result:hello from microphone"
