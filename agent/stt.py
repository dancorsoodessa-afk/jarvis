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
import threading

DEFAULT_LOCAL_MODEL = "small"
DEFAULT_STT_MODEL = "gemini-3.8-flash"
DEFAULT_GROQ_STT_MODEL = "whisper-large-v3-turbo"
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_QUOTA_EXCEEDED = False
_QUOTA_LOCK = threading.Lock()
QUOTA_MESSAGE = "Ошибка распознавания Gemini: HTTP 429. Квота на сегодня исчерпана (free tier); голосовое распознавание недоступно до сброса квоты или смены ключа/тарифа."


def quota_exceeded() -> bool:
    with _QUOTA_LOCK:
        return _QUOTA_EXCEEDED


def _set_quota_exceeded(value: bool) -> None:
    global _QUOTA_EXCEEDED
    with _QUOTA_LOCK:
        _QUOTA_EXCEEDED = value

DEFAULT_STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/"


def _model() -> str:
    return (os.environ.get("GEMINI_STT_MODEL") or os.environ.get("JARVIS_STT_MODEL") or DEFAULT_STT_MODEL).strip()


def _token() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def _groq_token() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


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
    if _groq_token():
        engines.append("groq")
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
        # Use the independent cloud reserve only after Gemini explicitly reports quota exhaustion.
        # Never silently load a local model or switch providers without a configured Groq key.
        if quota_exceeded():
            return "groq" if _groq_token() else "off"
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
    if engine == "groq":
        return "GROQ_READY"
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
        if exc.code == 429 and any(marker in detail.lower() for marker in ("quota", "free_tier", "limit exceeded", "resource_exhausted")):
            _set_quota_exceeded(True)
            raise RuntimeError(QUOTA_MESSAGE) from exc
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


def _transcribe_groq(path: Path) -> str:
    """Transcribe with Groq Whisper; used only as an explicitly configured cloud reserve."""
    token = _groq_token()
    if not token:
        raise RuntimeError("Для резервного распознавания Groq нужен GROQ_API_KEY.")
    audio = path.read_bytes()
    if not audio:
        raise ValueError("Аудиофайл пустой.")
    if len(audio) > 25 * 1024 * 1024:
        raise ValueError("Аудиофайл превышает лимит Groq STT в 25 МБ.")
    boundary = "----JarvisSTTBoundary7MA4YWxkTrZu0gW"
    filename = path.name or "speech.wav"
    parts = [
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
         + (os.environ.get("JARVIS_STT_FALLBACK_MODEL") or DEFAULT_GROQ_STT_MODEL).strip()
         + "\r\n").encode("utf-8"),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nru\r\n").encode("utf-8"),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\njson\r\n").encode("utf-8"),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
         "Content-Type: audio/wav\r\n\r\n").encode("utf-8"),
        audio,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    request = urllib.request.Request(
        GROQ_STT_URL, data=b"".join(parts),
        headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Accept": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_request_timeout()) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Резервное распознавание Groq: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к резервному распознаванию Groq: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Groq STT вернул некорректный JSON.") from exc
    text = str(result.get("text") or "").strip() if isinstance(result, dict) else ""
    if not text:
        raise RuntimeError("Groq Whisper не вернул распознанный текст.")
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
        try:
            return _transcribe_gemini(path)
        except RuntimeError:
            if quota_exceeded() and _groq_token():
                return _transcribe_groq(path)
            raise
    if engine == "groq":
        return _transcribe_groq(path)
    raise RuntimeError("Неизвестный режим распознавания речи.")
