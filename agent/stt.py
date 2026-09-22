"""Локальное распознавание речи JARVIS.

Единственный STT-движок: faster-whisper.
Модель поставляется вместе с Windows-сборкой, поэтому сеть для STT не нужна.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_MODEL = None
_MODEL_LOCK = threading.Lock()


def _model_dir() -> Path:
    override = os.environ.get("JARVIS_STT_MODEL_PATH", "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "stt_model"
    return Path(__file__).resolve().parent.parent / "vendor" / "stt_model"


def available_engines() -> list[str]:
    try:
        import faster_whisper  # noqa: F401
        return ["faster-whisper"]
    except ImportError:
        return []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "faster-whisper").strip().lower()
    if mode == "off":
        return "off"
    return "faster-whisper" if "faster-whisper" in available_engines() else "off"


def _get_model():
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("faster-whisper не установлен") from exc

            model_path = _model_dir()
            source = str(model_path) if model_path.exists() else "small"
            _MODEL = WhisperModel(
                source,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(1, int(os.environ.get("JARVIS_STT_THREADS", "6") or 6)),
                num_workers=1,
            )
    return _MODEL


def transcribe(audio_path: str) -> str:
    if current_engine() == "off":
        raise RuntimeError("Распознавание речи отключено или faster-whisper не установлен.")

    path = Path(audio_path)
    if not path.exists():
        raise ValueError(f"Файл не найден: {audio_path}")

    model = _get_model()
    segments, _info = model.transcribe(
        str(path),
        language="ru",
        beam_size=3,
        best_of=3,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 100},
        condition_on_previous_text=False,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()
