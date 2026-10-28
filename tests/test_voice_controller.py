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
    controller.shutdown()


def test_final_transcript_is_delivered_without_gui_access():
    events = queue.Queue()
    seen = []
    controller = VoiceController(UIBridge(events), on_text=seen.append)
    controller.on_text("  открой браузер  ")
    assert seen == ["открой браузер"]
    assert events.get_nowait() == ("voice_state", "UNDERSTANDING", "")
    controller.shutdown()


def test_empty_transcript_is_reported_not_silently_dropped():
    events = queue.Queue()
    controller = VoiceController(UIBridge(events), on_text=lambda _text: None)
    controller.on_text("   ")
    assert events.get_nowait() == ("voice_status", "Речь не распознана. Продолжаю слушать.")
    controller.shutdown()



def test_controller_exposes_gui_called_state_methods_on_correct_object():
    controller = VoiceController(UIBridge(queue.Queue()), on_text=lambda _text: None)
    assert callable(controller.mark_thinking)
    assert callable(controller.complete_without_speech)
    assert callable(controller.report_error)
    assert not hasattr(controller.tts_engine, "mark_thinking")
    controller.shutdown()


def test_ten_final_transcripts_are_routed_without_restarting_controller():
    events = queue.Queue()
    routed = []
    controller = VoiceController(UIBridge(events), on_text=routed.append)
    commands = [f"команда номер {index}" for index in range(1, 11)]
    for command in commands:
        controller.on_text(command)
    assert routed == commands
    assert controller.status()["running"] is False
    controller.shutdown()


def test_stop_voice_command_transitions_to_idle():
    events = queue.Queue()
    controller = VoiceController(UIBridge(events), on_text=lambda _text: None)
    controller.start = lambda: None  # This test verifies the command handler without opening a device.
    controller._running = True
    controller.on_text("стоп голос")
    assert controller.status()["state"] == "IDLE"
    assert controller.status()["running"] is False
    controller.shutdown()



def test_status_reports_cloud_voice_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_CHAT_KEY", raising=False)
    events = queue.Queue()
    controller = VoiceController(UIBridge(events), on_text=lambda _text: None)
    status = controller.status()
    assert status["cloud_voice_available"] is False
    assert status["state"] == "IDLE"
    controller.shutdown()



def test_status_reports_groq_as_cloud_stt_reserve(monkeypatch):
    from agent import stt, tts
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-token")
    monkeypatch.setattr(stt, "current_engine", lambda: "groq")
    monkeypatch.setattr(stt, "quota_exceeded", lambda: True)
    monkeypatch.setattr(tts, "current_engine", lambda: "gemini")
    controller = VoiceController(UIBridge(queue.Queue()), on_text=lambda _text: None)
    status = controller.status()
    assert status["cloud_voice_available"] is True
    assert status["cloud_stt_status"] == "cloud stt reserve: Groq"
    assert status["cloud_stt"] == "groq"
    assert status["quota_exceeded"] is True
    controller.shutdown()



def test_status_reports_tts_off_after_tts_failure(monkeypatch):
    from agent import stt, tts
    monkeypatch.setattr(stt, "current_engine", lambda: "gemini")
    monkeypatch.setattr(stt, "quota_exceeded", lambda: False)
    monkeypatch.setattr(tts, "current_engine", lambda: "gemini")
    controller = VoiceController(UIBridge(queue.Queue()), on_text=lambda _text: None)
    controller._tts_off = True
    status = controller.status()
    assert status["tts_status"] == "tts off"
    assert status["tts"] == "off"
    assert status["cloud_voice_available"] is False
    controller.shutdown()
