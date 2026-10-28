"""Quota-free local Whisper speech recognition by default; cloud engines are opt-in."""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_LOCAL_MODEL = "small"

def _local_available():
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False

def available_engines():
    result = ["local"] if _local_available() else []
    if (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY")):
        result.append("gemini")
    if os.environ.get("GROQ_API_KEY"):
        result.append("groq")
    return result

def current_engine():
    mode = os.environ.get("JARVIS_STT", "local").strip().lower()
    if mode == "off":
        return "off"
    if mode in ("local", "auto"):
        # Auto deliberately does not silently fall back to a quota-limited cloud service.
        return "local" if _local_available() else "off"
    if mode == "gemini":
        return "gemini" if (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY")) else "off"
    if mode == "groq":
        return "groq" if os.environ.get("GROQ_API_KEY") else "off"
    return "off"

@lru_cache(maxsize=2)
def _model(name):
    from faster_whisper import WhisperModel
    cache = os.environ.get("JARVIS_WHISPER_CACHE", "").strip() or None
    return WhisperModel(name, device="cpu", compute_type="int8", download_root=cache)

def health_check(timeout=10.0):
    engine = current_engine()
    if engine == "local":
        return "LOCAL_READY"
    if engine == "off":
        raise RuntimeError("Локальный Whisper недоступен. Установите JARVIS с компонентом voice.")
    return "CLOUD_SELECTED"

def warmup():
    health_check()

def transcribe(audio_path: str) -> str:
    engine = current_engine()
    path = Path(audio_path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {audio_path}")
    if engine == "local":
        name = (os.environ.get("JARVIS_WHISPER_MODEL") or DEFAULT_LOCAL_MODEL).strip()
        try:
            model = _model(name)
            segments, _ = model.transcribe(str(path), language="ru", beam_size=5, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            raise RuntimeError("Локальный Whisper не запустился. При первом запуске скачивается модель; "
                               f"проверьте интернет и место на диске. Детали: {exc}") from exc
        if not text:
            raise RuntimeError("Whisper не распознал речь. Проверьте микрофон и повторите.")
        return text
    if engine == "gemini":
        raise RuntimeError("Облачное распознавание Gemini отключено в этом режиме. Для него задайте JARVIS_STT=gemini; учитывайте квоты API.")
    if engine == "groq":
        raise RuntimeError("Облачное распознавание Groq отключено в этом режиме. Для него задайте JARVIS_STT=groq; учитывайте квоты API.")
    raise RuntimeError("Распознавание недоступно. Установите JARVIS с компонентом локального Whisper.")
