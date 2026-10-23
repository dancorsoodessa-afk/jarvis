"""Cloud speech-to-text using Gemini audio understanding; no local model."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_STT_MODEL = "gemini-3.8-flash"
DEFAULT_STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/"


def _token() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def available_engines() -> list[str]:
    return ["gemini"] if _token() else []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "auto").strip().lower()
    if mode == "off":
        return "off"
    return "gemini" if _token() else "off"


def health_check(timeout: float = 10.0) -> str:
    """Verify Gemini credentials, model availability, and network reachability without transcribing audio."""
    token = _token()
    if not token:
        raise RuntimeError("Не задан GEMINI_API_KEY для облачного распознавания речи.")
    url = DEFAULT_STT_URL + DEFAULT_STT_MODEL + "?" + urllib.parse.urlencode({"key": token})
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, min(20.0, float(timeout)))) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict) or not body.get("name"):
            raise RuntimeError("Gemini STT вернул неожиданный ответ проверки модели.")
        return "ONLINE"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Gemini STT: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini STT: сеть недоступна ({exc.reason}).") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Gemini STT вернул некорректный JSON при проверке доступности.") from exc


def warmup() -> None:
    health_check()


def _request_timeout() -> float:
    try:
        return max(5.0, min(180.0, float(os.environ.get("JARVIS_STT_TIMEOUT", "45") or "45")))
    except (TypeError, ValueError):
        return 45.0


def transcribe(audio_path: str) -> str:
    token = _token()
    if current_engine() == "off" or not token:
        raise RuntimeError("Голосовой ввод требует бесплатный GEMINI_API_KEY из Google AI Studio. Вставьте его в Центр управления.")
    path = Path(audio_path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {audio_path}")
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
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode("ascii")}}
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}
    }
    url = DEFAULT_STT_URL + DEFAULT_STT_MODEL + ":generateContent?" + urllib.parse.urlencode({"key": token})
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Accept": "application/json"},
                                     method="POST")
    result = None
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=_request_timeout()) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code in retryable and attempt < 2:
                import time
                time.sleep(1.0 * (2 ** attempt))
                continue
            raise RuntimeError(f"Ошибка распознавания Gemini: HTTP {exc.code}. {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt < 2:
                import time
                time.sleep(1.0 * (2 ** attempt))
                continue
            raise RuntimeError(f"Не удалось подключиться к Gemini STT: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Gemini STT вернул некорректный JSON.") from exc
    if result is None:
        raise RuntimeError("Gemini STT временно недоступен после повторных попыток.")
    try:
        text = "".join(part.get("text", "") for part in result["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        text = ""
    if text.strip():
        return text.strip()
    raise RuntimeError("Gemini не вернул распознанный текст. Проверьте качество аудио и лимит API.")
