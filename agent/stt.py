"""Cloud speech-to-text through the Google Gemini API.

Audio is read locally and sent to Gemini for transcription. No speech model is
downloaded or run on the PC.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_STT_MODEL = "gemini-2.5-flash"
DEFAULT_STT_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _token() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def available_engines() -> list[str]:
    return ["gemini"] if _token() else []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "gemini").strip().lower()
    if mode == "off":
        return "off"
    return "gemini" if _token() else "off"


def warmup() -> None:
    """No local model to warm up."""


def transcribe(audio_path: str) -> str:
    if current_engine() == "off":
        raise RuntimeError("Облачное распознавание речи недоступно: задайте GEMINI_API_KEY или включите текстовый ввод.")
    path = Path(audio_path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {audio_path}")
    token = _token()
    data = path.read_bytes()
    if not data:
        raise ValueError("Аудиофайл пустой.")
    url = os.environ.get("JARVIS_STT_URL", DEFAULT_STT_URL).strip().rstrip("/")
    if not url.startswith("https://generativelanguage.googleapis.com/"):
        raise RuntimeError("Распознавание речи разрешено только через Google Gemini API.")
    endpoint = f"{url}/{DEFAULT_STT_MODEL}:generateContent?{urllib.parse.urlencode({'key': token})}"
    payload = {
        "contents": [{
            "parts": [
                {"text": "Точно распознай речь в аудиозаписи. Верни только распознанные слова без комментариев."},
                {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(data).decode("ascii")}},
            ]
        }]
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Ошибка облачного распознавания речи: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к облачному распознаванию речи: {exc.reason}") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Сервис распознавания вернул неподдерживаемый ответ.") from exc
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = " ".join(str(part.get("text", "")).strip() for part in parts if isinstance(part, dict)).strip()
    except (KeyError, IndexError, TypeError):
        text = ""
    if text:
        return text
    error = payload.get("error") if isinstance(payload, dict) else None
    if error:
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        raise RuntimeError(f"Ошибка Gemini STT: {message[:400]}")
    raise RuntimeError("Gemini не вернул распознанный текст.")
