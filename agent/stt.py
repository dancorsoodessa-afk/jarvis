"""Speech-to-text for Jarvis (opt-in, mirrors agent/tts.py strategy).

Engines:
  1. whisper.cpp CLI  (JARVIS_STT=whisper-cpp, JARVIS_WHISPER=path,
                       JARVIS_WHISPER_MODEL=path/to/ggml-model.bin)
     — fits the project's local llama.cpp + Vulkan strategy.
  2. faster-whisper Python package (JARVIS_STT=faster-whisper; lazy import).
  3. Off (JARVIS_STT=off) — default.

transcribe(path) -> text. Network-free for both engines.
"""

import os
import subprocess
import sys
from pathlib import Path


def available_engines() -> list[str]:
    engines = []
    if os.environ.get("JARVIS_WHISPER"):
        engines.append("whisper-cpp")
    try:
        import faster_whisper  # noqa: F401
        engines.append("faster-whisper")
    except ImportError:
        pass
    return engines


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "off").lower()
    if mode == "auto":
        engines = available_engines()
        return engines[0] if engines else "off"
    return mode


def _run_whisper_cpp(wav_path: Path) -> str:
    exe = os.environ.get("JARVIS_WHISPER")
    model = os.environ.get("JARVIS_WHISPER_MODEL", "")
    if not exe or not Path(exe).exists():
        raise RuntimeError(f"whisper.cpp не найден: {exe}")
    if not model or not Path(model).exists():
        raise RuntimeError(f"Модель whisper не найдена: {model}")
    proc = subprocess.run(
        [exe, "-m", model, "-f", str(wav_path), "-nt", "-l", "ru"],
        capture_output=True, timeout=300)
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(f"whisper.cpp ошибка: {proc.stderr.decode('utf-8', errors='replace')[:200]}")
    return text


def _run_faster_whisper(wav_path: Path) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper не установлен: poetry add faster-whisper") from exc
    model_size = os.environ.get("JARVIS_STT_MODEL_SIZE", "small")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav_path), language="ru")
    return " ".join(seg.text.strip() for seg in segments).strip()


def transcribe(audio_path: str) -> str:
    """Transcribe a wav file to text."""
    engine = current_engine()
    if engine == "off":
        raise RuntimeError(
            "STT отключён (JARVIS_STT=off). Доступно: "
            + (", ".join(available_engines()) or "нет установленных движков"))
    path = Path(audio_path)
    if not path.exists():
        raise ValueError(f"Файл не найден: {audio_path}")
    if engine == "whisper-cpp":
        return _run_whisper_cpp(path)
    if engine == "faster-whisper":
        return _run_faster_whisper(path)
    raise RuntimeError(f"Неизвестный STT-движок: {engine}")
