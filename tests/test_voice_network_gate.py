from __future__ import annotations

import pytest

from agent import connectivity, stt, tts, voice


def test_stt_is_disabled_when_offline(monkeypatch):
    monkeypatch.setattr(connectivity, "internet_available", lambda: False)
    assert stt.current_engine() == "off"
    with pytest.raises(RuntimeError, match="Интернет недоступен"):
        stt.transcribe("does-not-need-to-exist.wav")


def test_microphone_is_unavailable_when_offline(monkeypatch):
    monkeypatch.setattr(connectivity, "internet_available", lambda: False)
    assert voice.available() is False


def test_tts_is_disabled_when_offline(monkeypatch):
    monkeypatch.setattr(connectivity, "internet_available", lambda: False)
    assert tts.current_engine() == "off"
    with pytest.raises(RuntimeError, match="Интернет недоступен"):
        tts.speak("Проверка")
