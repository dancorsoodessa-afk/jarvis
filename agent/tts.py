"""TTS JARVIS: локальный мужской голос по умолчанию + ElevenLabs как опция.

Локальный Piper не зависит от интернет-лимитов и подходит для непрерывного
разговора весь день. ElevenLabs можно включить вручную через JARVIS_TTS=elevenlabs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import wave
from pathlib import Path

_PLAYBACK_LOCK = threading.Lock()
_PLAYBACK_ACTIVE = False
DEFAULT_ELEVEN_VOICE = "srULqtwUV9XZPg1ZCO5w"
DEFAULT_ELEVEN_MODEL = "eleven_flash_v2_5"
DEFAULT_ELEVEN_FORMAT = "pcm_22050"


def _piper_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "piper"
    return Path(__file__).resolve().parent.parent / "vendor" / "piper"


def _piper_paths() -> tuple[str, Path]:
    configured = os.environ.get("JARVIS_PIPER", "").strip()
    executable = Path(configured) if configured else _piper_dir() / "piper.exe"
    voice = Path(os.environ.get(
        "JARVIS_PIPER_VOICE",
        str(_piper_dir() / "ru_RU-dmitri-medium.onnx"),
    ))
    if not executable.exists():
        raise RuntimeError(f"Piper не найден: {executable}")
    if not voice.exists():
        raise RuntimeError(f"Русская модель голоса Dmitri не найдена: {voice}")
    return str(executable), voice


def _eleven_key() -> str:
    return (
        os.environ.get("JARVIS_ELEVENLABS_API_KEY")
        or os.environ.get("ELEVENLABS_API_KEY")
        or ""
    ).strip()


def _eleven_voice() -> str:
    return (
        os.environ.get("JARVIS_ELEVENLABS_VOICE_ID")
        or DEFAULT_ELEVEN_VOICE
    ).strip()


def _eleven_model() -> str:
    return (
        os.environ.get("JARVIS_ELEVENLABS_MODEL")
        or DEFAULT_ELEVEN_MODEL
    ).strip()


def set_gender(gender: str) -> None:
    value = str(gender).strip().lower()
    if value not in {"male", "мужской", ""}:
        raise ValueError("В этой сборке установлен русский мужской голос.")
    os.environ["JARVIS_TTS_GENDER"] = "male"


def _engine_setting() -> str:
    return os.environ.get("JARVIS_TTS", "local").strip().lower()


def available_engines() -> list[str]:
    result = []
    try:
        _piper_paths()
        result.append("piper")
    except Exception:
        pass
    if _eleven_key() and _eleven_voice():
        result.append("elevenlabs")
    return result


def current_engine() -> str:
    mode = _engine_setting()
    if mode == "elevenlabs":
        return "elevenlabs" if "elevenlabs" in available_engines() else "piper"
    if mode in {"local", "piper"}:
        return "piper" if "piper" in available_engines() else "off"
    if mode == "off":
        return "off"
    if mode == "auto":
        # Backward-compatible alias, but local is preferred to avoid cloud quotas.
        return "piper" if "piper" in available_engines() else (
            "elevenlabs" if "elevenlabs" in available_engines() else "off"
        )
    raise RuntimeError(f"Неизвестный TTS-движок: {mode}")


def stop() -> None:
    global _PLAYBACK_ACTIVE
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass
    with _PLAYBACK_LOCK:
        _PLAYBACK_ACTIVE = False


def is_playing() -> bool:
    with _PLAYBACK_LOCK:
        return _PLAYBACK_ACTIVE


def _speak_piper(text: str) -> Path:
    piper, voice = _piper_paths()
    out = Path(tempfile.gettempdir()) / "jarvis_tts.wav"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with open(out, "wb") as wav:
        subprocess.run(
            [piper, "--model", str(voice), "--output_file", str(out)],
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
            timeout=60,
            creationflags=flags,
        )
    return out


def _speak_elevenlabs(text: str) -> Path:
    key = _eleven_key()
    voice = _eleven_voice()
    if not key:
        raise RuntimeError("ElevenLabs API-ключ не задан.")
    if not voice:
        raise RuntimeError("ElevenLabs Voice ID не задан.")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format={DEFAULT_ELEVEN_FORMAT}"
    payload = json.dumps({
        "text": text,
        "model_id": _eleven_model(),
        "language_code": "ru",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/pcm",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            pcm = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ElevenLabs HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ElevenLabs сеть недоступна: {exc.reason}") from exc
    out = Path(tempfile.gettempdir()) / "jarvis_tts_eleven.wav"
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(pcm)
    return out


def speak(text: str) -> Path:
    text = " ".join(str(text).split())
    if not text:
        raise RuntimeError("Пустой текст для озвучки.")
    # No conversational/session limit; keep only a per-response safety bound.
    text = text[:4000]
    engine = current_engine()
    if engine == "elevenlabs":
        try:
            return _speak_elevenlabs(text)
        except Exception:
            if "piper" not in available_engines():
                raise
            return _speak_piper(text)
    if engine == "piper":
        return _speak_piper(text)
    raise RuntimeError("TTS недоступен.")


def speak_and_play(text: str) -> Path:
    global _PLAYBACK_ACTIVE
    path = speak(text)
    if sys.platform != "win32":
        return path
    import winsound

    with _PLAYBACK_LOCK:
        _PLAYBACK_ACTIVE = True
    try:
        # Async playback lets the microphone/VAD stop speech immediately.
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_ASYNC,
        )
        while is_playing():
            # The VAD callback calls stop() on user speech.
            import time
            time.sleep(0.03)
            # winsound does not expose reliable completion state. The audio
            # file duration is therefore polled and stop() remains immediate.
            try:
                with wave.open(str(path), "rb") as wav:
                    duration = wav.getnframes() / max(1, wav.getframerate())
            except Exception:
                duration = 0.0
            if duration > 0:
                time.sleep(duration)
                break
    finally:
        with _PLAYBACK_LOCK:
            _PLAYBACK_ACTIVE = False
    return path
