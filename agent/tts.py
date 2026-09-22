"""Локальный text-to-speech для JARVIS.

Единственный TTS-движок: Piper + русский мужской голос Dmitri Medium.
Никаких облачных TTS, API-ключей или нескольких конкурирующих движков.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_PLAYBACK_LOCK = threading.Lock()
_PLAYBACK_ACTIVE = False


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


def available_engines() -> list[str]:
    try:
        _piper_paths()
        return ["piper"]
    except Exception:
        return []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_TTS", "piper").strip().lower()
    return "piper" if mode != "off" and available_engines() else "off"


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


def speak(text: str) -> Path:
    if current_engine() == "off":
        raise RuntimeError("Piper TTS недоступен.")
    text = " ".join(str(text).split())[:1000]
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


def speak_and_play(text: str) -> Path:
    global _PLAYBACK_ACTIVE
    path = speak(text)
    if sys.platform != "win32":
        return path
    import winsound
    with _PLAYBACK_LOCK:
        _PLAYBACK_ACTIVE = True
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    finally:
        with _PLAYBACK_LOCK:
            _PLAYBACK_ACTIVE = False
    return path
