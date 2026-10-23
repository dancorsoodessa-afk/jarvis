"""Cloud speech-to-text via GroqCloud Whisper API; no local STT model."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_STT_MODEL = "whisper-large-v3-turbo"
DEFAULT_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _token() -> str:
    return (os.environ.get("GROQ_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def available_engines() -> list[str]:
    return ["groq"] if _token() else []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "auto").strip().lower()
    if mode == "off":
        return "off"
    return "groq" if _token() else "off"


def warmup() -> None:
    """No local model to warm up."""


def transcribe(audio_path: str) -> str:
    if current_engine() == "off":
        raise RuntimeError("Голосовой ввод требует бесплатный ключ GroqCloud. Вставьте его в Центре управления.")
    path = Path(audio_path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {audio_path}")
    audio = path.read_bytes()
    if not audio:
        raise ValueError("Аудиофайл пустой.")

    boundary = "----JARVIS" + uuid.uuid4().hex
    body = bytearray()
    for name, value in (("model", DEFAULT_STT_MODEL), ("response_format", "json"), ("language", "ru")):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode())
    body.extend(b"Content-Type: audio/wav\r\n\r\n")
    body.extend(audio)
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    url = os.environ.get("JARVIS_STT_URL", DEFAULT_STT_URL).strip()
    if not url.startswith("https://api.groq.com/openai/v1/audio/transcriptions"):
        raise RuntimeError("Голосовое распознавание разрешено только через HTTPS API GroqCloud.")
    request = urllib.request.Request(
        url, data=bytes(body),
        headers={"Authorization": f"Bearer {_token()}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Ошибка распознавания GroqCloud: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к распознаванию GroqCloud: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Сервис распознавания вернул некорректный ответ.") from exc

    text = payload.get("text") if isinstance(payload, dict) else None
    if isinstance(text, str) and text.strip():
        return text.strip()
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"Ошибка GroqCloud STT: {str(payload['error'])[:400]}")
    raise RuntimeError("Сервис распознавания не вернул распознанный текст.")
