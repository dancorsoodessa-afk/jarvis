"""Cloud speech-to-text via Hugging Face Inference Providers.

Microphone capture remains local; speech recognition is performed remotely.
No Whisper model is downloaded or loaded on the PC.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_STT_MODEL = "openai/whisper-large-v3-turbo"
DEFAULT_STT_URL = f"https://router.huggingface.co/hf-inference/models/{DEFAULT_STT_MODEL}"


def _token() -> str:
    return (os.environ.get("HF_TOKEN") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def available_engines() -> list[str]:
    return ["huggingface"] if _token() else []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "huggingface").strip().lower()
    if mode == "off":
        return "off"
    return "huggingface" if _token() else "off"


def warmup() -> None:
    """No local model to warm up."""


def transcribe(audio_path: str) -> str:
    if current_engine() == "off":
        raise RuntimeError("Облачное распознавание речи недоступно: задайте HF_TOKEN или включите текстовый ввод.")
    path = Path(audio_path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {audio_path}")
    token = _token()
    url = os.environ.get("JARVIS_STT_URL", DEFAULT_STT_URL).strip()
    if not url.startswith("https://router.huggingface.co/"):
        raise RuntimeError("Распознавание речи разрешено только через Hugging Face Router.")
    data = path.read_bytes()
    if not data:
        raise ValueError("Аудиофайл пустой.")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "audio/wav", "Accept": "application/json"},
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
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Сервис распознавания вернул неподдерживаемый ответ.")
    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        if payload.get("error"):
            raise RuntimeError(f"Ошибка Hugging Face STT: {str(payload['error'])[:400]}")
    raise RuntimeError("Сервис распознавания не вернул распознанный текст.")
