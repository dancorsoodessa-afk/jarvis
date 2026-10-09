from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]


def test_python_sources_parse():
    failures = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", "venv", "__pycache__", "build", "dist"} for part in path.parts):
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path}: {exc}")
    assert not failures, "\n".join(failures)


def test_voice_has_no_clap_activation():
    source = (ROOT / "agent" / "voice.py").read_text(encoding="utf-8").lower()
    assert "detect_clap" not in source


def test_tts_has_gender_compatibility():
    source = (ROOT / "agent" / "tts.py").read_text(encoding="utf-8")
    assert "def set_gender" in source
    assert "api.elevenlabs.io/v1/text-to-speech" in source
    assert "JARVIS_ELEVENLABS_API_KEY" in source
    assert "eleven_flash_v2_5" in source
    assert "pcm_22050" in source



def test_desktop_passes_attachment_to_agent():
    source = (ROOT / "jarvis_desktop.py").read_text(encoding="utf-8")
    assert "attachment=attachment_payload" in source
    assert "_build_attachment_payload" in source



def test_desktop_preserves_explicit_local_api_endpoint():
    source = (ROOT / "jarvis_desktop.py").read_text(encoding="utf-8")
    assert 'return url or DEFAULT_URL' in source
    assert 'blocked = ("localhost", "127.0.0.1", "0.0.0.0")' not in source


def test_voice_zero_start_timeout_does_not_immediately_return():
    source = (ROOT / "agent" / "voice.py").read_text(encoding="utf-8")
    assert "timeout_blocks = max(0, int(start_timeout / BLOCK_SECONDS))" in source
    assert "elif timeout_blocks and idle_blocks >= timeout_blocks:" in source


def test_desktop_tts_worker_does_not_touch_tk_widgets():
    source = (ROOT / "jarvis_desktop.py").read_text(encoding="utf-8")
    start = source.index("    def _speak_reply(self, text):")
    end = source.index("    def _replace_streaming_reply", start)
    worker = source[start:end]
    assert "tts.speak_and_play(text)" in worker
    assert "self._set_visual_state" not in worker


def test_desktop_request_failures_are_not_reported_as_online_replies():
    source = (ROOT / "jarvis_desktop.py").read_text(encoding="utf-8")
    assert 'self.events.put(("request_error", str(exc)))' in source
    assert 'self.status.config(text="● API ERROR", fg=RED)' in source
    assert 'self._append("AI", "Запрос не выполнен: " + event[1])' in source


def test_desktop_event_pump_survives_handler_exceptions():
    source = (ROOT / "jarvis_desktop.py").read_text(encoding="utf-8")
    assert "A malformed UI event must not stop all future replies/events." in source
    assert "finally:\n            try:\n                self.after(80, self._drain_events)" in source
