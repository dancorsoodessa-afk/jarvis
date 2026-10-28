from __future__ import annotations

import queue

from agent.voice_controller import MicLock, UIBridge, VoiceController


def test_ui_bridge_only_enqueues_events():
    events = queue.Queue()
    bridge = UIBridge(events)
    bridge.post("voice_state", "LISTENING", "")
    assert events.get_nowait() == ("voice_state", "LISTENING", "")


def test_mic_lock_rejects_second_owner_until_released():
    lock = MicLock()
    lock.acquire("capture")
    try:
        try:
            lock.acquire("second")
        except RuntimeError as exc:
            assert "already" in str(exc).lower() or "занят" in str(exc).lower()
        else:
            raise AssertionError("MicLock accepted a second simultaneous owner")
    finally:
        lock.release()
    lock.acquire("capture-again")
    lock.release()


def test_voice_controller_starts_idle_and_reports_status():
    controller = VoiceController(UIBridge(queue.Queue()), on_text=lambda _text: None)
    status = controller.status()
    assert status["state"] == "IDLE"
    assert status["running"] is False
    assert status["is_speaking"] is False
    assert status["mic"] == "fail"


def test_final_transcript_is_delivered_without_gui_access():
    events = queue.Queue()
    seen = []
    controller = VoiceController(UIBridge(events), on_text=seen.append)
    controller.on_text("  открой браузер  ")
    assert seen == ["открой браузер"]
    assert events.get_nowait() == ("voice_state", "UNDERSTANDING", "")


def test_empty_transcript_is_reported_not_silently_dropped():
    events = queue.Queue()
    controller = VoiceController(UIBridge(events), on_text=lambda _text: None)
    controller.on_text("   ")
    assert events.get_nowait() == ("voice_status", "Речь не распознана. Продолжаю слушать.")
