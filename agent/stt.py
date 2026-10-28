"""Speech-to-text: Gemini cloud recognition by default; local Whisper is opt-in only."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

DEFAULT_LOCAL_MODEL = "small"
DEFAULT_STT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/"


def _model() -> str:
    return (os.environ.get("JARVIS_STT_MODEL") or DEFAULT_STT_MODEL).strip()


def _token() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def _local_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def available_engines() -> list[str]:
    engines = []
    if _token():
        engines.append("gemini")
    if _local_available():
        engines.append("local")
    return engines


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "gemini").strip().lower()
    if mode == "off":
        return "off"
    if mode in ("local", "whisper"):
        return "local" if _local_available() else "off"
    if mode in ("gemini", "cloud", "auto"):
        # Cloud-first: never silently switch providers or download a local model.
        return "gemini" if _token() else "off"
    return "off"


def _request_timeout() -> float:
    try:
        return max(5.0, min(180.0, float(os.environ.get("JARVIS_STT_TIMEOUT", "45") or "45")))
    except (TypeError, ValueError):
        return 45.0


@lru_cache(maxsize=2)
def _local_model(name: str):
    from faster_whisper import WhisperModel
    cache = os.environ.get("JARVIS_WHISPER_CACHE", "").strip() or None
    return WhisperModel(name, device="cpu", compute_type="int8", download_root=cache)


def health_check(timeout: float = 10.0) -> str:
    engine = current_engine()
    if engine == "local":
        return "LOCAL_READY"
    if engine == "off":
        raise RuntimeError("Распознавание речи недоступно: проверьте GEMINI_API_KEY или явно включите локальный Whisper.")
    return "CLOUD_SELECTED"


def warmup() -> None:
    health_check()


def _transcribe_gemini(path: Path) -> str:
    token = _token()
    if not token:
        raise RuntimeError("Не задан GEMINI_API_KEY для распознавания речи.")
    audio = path.read_bytes()
    if not audio:
        raise ValueError("Аудиофайл пустой.")
    if len(audio) > 18 * 1024 * 1024:
        raise ValueError("Аудиофайл слишком большой для одного запроса Gemini (лимит JARVIS — 18 МБ).")
    suffix = path.suffix.lower()
    mime = "audio/wav" if suffix == ".wav" else "audio/mpeg" if suffix == ".mp3" else "audio/" + suffix.lstrip(".")
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": "Точно распознай речь в аудио. Язык русский. Верни только распознанные слова без комментариев."},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode("ascii")}},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024},
    }
    url = DEFAULT_STT_URL + _model() + ":generateContent?" + urllib.parse.urlencode({"key": token})
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_request_timeout()) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Ошибка распознавания Gemini: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к Gemini STT: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Gemini STT вернул некорректный JSON.") from exc
    try:
        text = "".join(part.get("text", "") for part in result["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        raise RuntimeError("Gemini не вернул распознанный текст.")
    return text


def transcribe(audio_path: str) -> str:
    engine = current_engine()
    if engine == "off":
        raise RuntimeError("Распознавание речи отключено или недоступно. Проверьте GEMINI_API_KEY и интернет.")
    path = Path(audio_path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {audio_path}")
    if engine == "local":
        name = (os.environ.get("JARVIS_WHISPER_MODEL") or DEFAULT_LOCAL_MODEL).strip()
        try:
            model = _local_model(name)
            segments, _ = model.transcribe(str(path), language="ru", beam_size=5, vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise RuntimeError("Локальный Whisper не запустился. Детали: " + str(exc)) from exc
        if not text:
            raise RuntimeError("Whisper не распознал речь. Проверьте микрофон и повторите.")
        return text
    if engine == "gemini":
        return _transcribe_gemini(path)
    raise RuntimeError("Неизвестный режим распознавания речи.")
