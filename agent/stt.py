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


def warmup() -> None:
    """No local model to warm up."""


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
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Ошибка распознавания Gemini: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к Gemini STT: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Gemini STT вернул некорректный JSON.") from exc
    try:
        text = "".join(part.get("text", "") for part in result["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        text = ""
    if text.strip():
        return text.strip()
    raise RuntimeError("Gemini не вернул распознанный текст. Проверьте качество аудио и лимит API.")
