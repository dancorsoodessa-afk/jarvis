"""Tests for the voice loop: wake-word gating and the hear->think->speak step."""

import pytest

from agent.voice_loop import VoiceLoop


from types import SimpleNamespace


class FakeAgent:
    name = "fake"

    def __init__(self):
        self.calls = []

    def handle(self, text):
        self.calls.append(text)
        return SimpleNamespace(text=f"ответ на {text}")


class FakeRecorder:
    def record(self, out_path):
        out_path.write_bytes(b"")
        return out_path


def make_loop(agent, **kw):
    return VoiceLoop(agent, recorder=FakeRecorder(),
                     tmp_dir="/tmp", **kw)


def test_wake_word_required():
    agent = FakeAgent()
    loop = make_loop(agent)
    assert loop.step("просто фраза без ворда") is None
    assert agent.calls == []


def test_wake_word_with_command():
    agent = FakeAgent()
    loop = make_loop(agent)
    out = loop.step("Джарвис, какая погода в Москве")
    assert agent.calls == ["какая погода в москве"]
    assert "погода" in out


def test_wake_word_alone_acknowledges():
    agent = FakeAgent()
    loop = make_loop(agent)
    assert loop.step("джарвис") == "Слушаю."
    assert agent.calls == []


def test_wake_disabled_passes_through():
    agent = FakeAgent()
    loop = make_loop(agent, wake_enabled=False)
    loop.step("обычная команда")
    assert agent.calls == ["обычная команда"]


def test_custom_wake_word():
    agent = FakeAgent()
    loop = make_loop(agent, wake_words=("альфред",))
    assert loop.step("джарвис включи свет") is None
    loop.step("Альфред, свет")
    assert agent.calls == ["свет"]


def test_step_agent_error_propagates():
    class Boom:
        name = "boom"

        def handle(self, text):
            raise RuntimeError("fail")

    loop = make_loop(Boom())
    with pytest.raises(RuntimeError):
        loop.step("джарвис привет")
