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
    assert "double_clap" in source  # compatibility alias only; it delegates to normal VAD


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
