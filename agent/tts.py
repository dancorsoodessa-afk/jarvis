"""Cloud-only text-to-speech via ElevenLabs.

No local TTS model or executable is bundled. Speech output is optional and requires
an ElevenLabs API key; text chat remains usable without it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

_PLAYBACK_LOCK = threading.Lock()
_PLAYBACK_ACTIVE = False
_PLAYBACK_TOKEN = 0
DEFAULT_ELEVEN_VOICE = "srULqtwUV9XZPg1ZCO5w"
DEFAULT_ELEVEN_MODEL = "eleven_flash_v2_5"


def _eleven_key() -> str:
    return (os.environ.get("JARVIS_ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY") or "").strip()


def _eleven_voice() -> str:
    return (os.environ.get("JARVIS_ELEVENLABS_VOICE_ID") or DEFAULT_ELEVEN_VOICE).strip()


def available_engines() -> list[str]:
    return ["elevenlabs"] if _eleven_key() and _eleven_voice() else []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_TTS", "auto").strip().lower()
    if mode == "off":
        return "off"
    if mode in {"auto", "elevenlabs", "cloud"}:
        return "elevenlabs" if available_engines() else "off"
    raise RuntimeError("Поддерживается только облачный TTS ElevenLabs; локальные движки отключены.")


def set_gender(gender: str) -> None:
    value = str(gender).strip().lower()
    if value not in {"male", "мужской", ""}:
        raise ValueError("Для выбранного облачного голоса доступна текущая конфигурация голоса.")


def stop() -> None:
    global _PLAYBACK_ACTIVE, _PLAYBACK_TOKEN
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass
    with _PLAYBACK_LOCK:
        _PLAYBACK_TOKEN += 1
        _PLAYBACK_ACTIVE = False


def is_playing() -> bool:
    with _PLAYBACK_LOCK:
        return _PLAYBACK_ACTIVE


def _temp_wav() -> Path:
    fd, name = tempfile.mkstemp(prefix="jarvis_tts_cloud_", suffix=".wav")
    os.close(fd)
    return Path(name)


def speak(text: str) -> Path:
    text = " ".join(str(text).split())[:4000]
    if not text:
        raise RuntimeError("Пустой текст для озвучки.")
    if current_engine() != "elevenlabs":
        raise RuntimeError("Облачная озвучка выключена или не настроена. Задайте ELEVENLABS_API_KEY.")
    voice = _eleven_voice()
    model = os.environ.get("JARVIS_ELEVENLABS_MODEL", DEFAULT_ELEVEN_MODEL).strip()
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_22050"
    payload = json.dumps({
        "text": text,
        "model_id": model,
        "language_code": "ru",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True},
    }).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload,
        headers={"xi-api-key": _eleven_key(), "Content-Type": "application/json", "Accept": "audio/pcm"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            pcm = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Ошибка облачной озвучки: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к облачной озвучке: {exc.reason}") from exc
    if not pcm:
        raise RuntimeError("Сервис озвучки вернул пустой аудиофайл.")
    out = _temp_wav()
    try:
        with wave.open(str(out), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(pcm)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    return out


def speak_and_play(text: str) -> Path:
    global _PLAYBACK_ACTIVE, _PLAYBACK_TOKEN
    path = speak(text)
    if sys.platform != "win32":
        return path
    import winsound
    stop()
    try:
        with wave.open(str(path), "rb") as wav:
            duration = wav.getnframes() / max(1, wav.getframerate())
    except Exception:
        duration = 0.0
    with _PLAYBACK_LOCK:
        token = _PLAYBACK_TOKEN
        _PLAYBACK_ACTIVE = True
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)

    def _cleanup() -> None:
        global _PLAYBACK_ACTIVE
        if duration:
            time.sleep(duration + 0.1)
        with _PLAYBACK_LOCK:
            if _PLAYBACK_TOKEN == token:
                _PLAYBACK_ACTIVE = False
        try:
            path.unlink()
        except OSError:
            pass

    threading.Thread(target=_cleanup, daemon=True).start()
    return path
