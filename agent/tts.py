"""Text-to-speech for Jarvis.

Strategy (per project performance rule — everything is opt-in):
  1. Piper  (JARVIS_TTS=piper,  JARVIS_PIPER=.../piper.exe, JARVIS_PIPER_VOICE=ru_RU-dmitri-medium.onnx)
     — best quality, local, fast even on CPU.
  2. Windows SAPI via PowerShell (default on Windows, zero install).
  3. Disabled (JARVIS_TTS=off) — default for tests/CI.

speak(text) returns the output file path (wav) without playing;
speak_and_play() also plays it. Callers must handle RuntimeError.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _piper_dir() -> Path:
    return Path(os.environ.get("JARVIS_HOME", ".")) / "voice"


def _run_piper(text: str, out_path: Path) -> Path:
    piper = os.environ.get("JARVIS_PIPER", "piper")
    voice = os.environ.get(
        "JARVIS_PIPER_VOICE", str(_piper_dir() / "ru_RU-dmitri-medium.onnx"))
    if not Path(voice).exists():
        raise RuntimeError(f"Голос piper не найден: {voice}")
    with open(out_path, "wb") as wav:
        subprocess.run([piper, "-m", voice, "-f", "-"],
                       input=text.encode("utf-8"), stdout=wav,
                       check=True, timeout=60)
    return out_path


def _run_windows_sapi(text: str, out_path: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("SAPI доступен только на Windows")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SetOutputToWaveFile('%s'); "
        "$s.Speak('%s'); "
        "$s.Dispose()" % (
            str(out_path).replace("'", "''"),
            text.replace("'", "''")[:500],
        )
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=True, timeout=120, capture_output=True)
    return out_path


def available_engines() -> list[str]:
    engines = []
    if os.environ.get("JARVIS_PIPER") or _piper_dir().joinpath(
            "ru_RU-dmitri-medium.onnx").exists():
        engines.append("piper")
    if sys.platform == "win32":
        engines.append("sapi")
    return engines


def current_engine() -> str:
    mode = os.environ.get("JARVIS_TTS", "auto").lower()
    if mode == "off":
        return "off"
    if mode == "auto":
        engines = available_engines()
        return engines[0] if engines else "off"
    return mode


def speak(text: str) -> Path:
    """Synthesize text to a wav file; returns the path."""
    engine = current_engine()
    if engine == "off":
        raise RuntimeError("TTS отключён (JARVIS_TTS=off)")
    text = " ".join(text.split())[:1000]
    out = Path(tempfile.gettempdir()) / "jarvis_tts.wav"
    if engine == "piper":
        return _run_piper(text, out)
    if engine == "sapi":
        return _run_windows_sapi(text, out)
    raise RuntimeError(f"Неизвестный TTS-движок: {engine}")


def speak_and_play(text: str) -> Path:
    """Synthesize and play the result. Returns the wav path."""
    path = speak(text)
    if sys.platform == "win32":
        ps = ("(New-Object Media.SoundPlayer '%s').PlaySync();"
              % str(path).replace("'", "''"))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=True, timeout=120, capture_output=True)
    return path
