"""Speech-to-text engines for JARVIS.

Priority:
1. whisper.cpp when JARVIS_WHISPER is configured (fully local).
2. faster-whisper when installed (local CPU, int8).
3. Voice module may use its lightweight network fallback when no local engine
   exists. STT itself never performs network requests.
"""

import os
import subprocess
from pathlib import Path


def available_engines() -> list[str]:
    engines = []
    exe = os.environ.get("JARVIS_WHISPER", "").strip()
    if exe and Path(exe).exists():
        engines.append("whisper-cpp")
    try:
        import faster_whisper  # noqa: F401
        engines.append("faster-whisper")
    except ImportError:
        pass
    return engines


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "auto").strip().lower()
    if mode == "auto":
        engines = available_engines()
        return engines[0] if engines else "off"
    if mode in {"off", "whisper-cpp", "faster-whisper"}:
        return mode
    return "off"


def _run_whisper_cpp(wav_path: Path) -> str:
    exe = os.environ.get("JARVIS_WHISPER", "").strip()
    model = os.environ.get("JARVIS_WHISPER_MODEL", "").strip()
    if not exe or not Path(exe).exists():
        raise RuntimeError(f"whisper.cpp не найден: {exe}")
    if not model or not Path(model).exists():
        raise RuntimeError(f"Модель whisper не найдена: {model}")
    proc = subprocess.run(
        [exe, "-m", model, "-f", str(wav_path), "-nt", "-l", "ru"],
        capture_output=True,
        timeout=120,
    )
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            "whisper.cpp ошибка: "
            + proc.stderr.decode("utf-8", errors="replace")[:300]
        )
    return text


def _run_faster_whisper(wav_path: Path) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper не установлен") from exc
    model_size = os.environ.get("JARVIS_STT_MODEL_SIZE", "tiny").strip() or "tiny"
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(wav_path),
        language="ru",
        beam_size=1,
        vad_filter=True,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def transcribe(audio_path: str) -> str:
    engine = current_engine()
    if engine == "off":
        raise RuntimeError(
            "Локальный STT не установлен. Используется резервное распознавание."
        )
    path = Path(audio_path)
    if not path.exists():
        raise ValueError(f"Файл не найден: {audio_path}")
    if engine == "whisper-cpp":
        return _run_whisper_cpp(path)
    if engine == "faster-whisper":
        return _run_faster_whisper(path)
    raise RuntimeError(f"Неизвестный STT-движок: {engine}")
