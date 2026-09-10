"""Fast local text-to-speech for JARVIS.

Silero is the preferred Russian TTS engine. The model is cached under
%APPDATA%\\JARVIS\\voice and loaded once per process. Windows SAPI is the
fallback in auto mode.
"""

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

SILERO_MODEL_URL = "https://models.silero.ai/models/tts/ru/v5_ru.pt"
DEFAULT_SILERO_VOICE = "eugene"
_PLAYBACK_LOCK = threading.Lock()
_PLAYBACK_PROCESS = None


def _voice_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "JARVIS" / "voice"


def _piper_dir() -> Path:
    return Path(os.environ.get("JARVIS_HOME", ".")) / "voice"


def stop() -> None:
    """Immediately stop currently playing JARVIS audio."""
    global _PLAYBACK_PROCESS
    with _PLAYBACK_LOCK:
        process = _PLAYBACK_PROCESS
        _PLAYBACK_PROCESS = None
    if process is not None and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=0.4)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


def is_playing() -> bool:
    with _PLAYBACK_LOCK:
        return _PLAYBACK_PROCESS is not None and _PLAYBACK_PROCESS.poll() is None


def _run_piper(text: str, out_path: Path) -> Path:
    piper = os.environ.get("JARVIS_PIPER", "piper")
    voice = os.environ.get("JARVIS_PIPER_VOICE", str(_piper_dir() / "ru_RU-dmitri-medium.onnx"))
    if not Path(voice).exists():
        raise RuntimeError(f"Голос piper не найден: {voice}")
    with open(out_path, "wb") as wav:
        subprocess.run([piper, "-m", voice, "-f", "-"], input=text.encode("utf-8"), stdout=wav, check=True, timeout=60)
    return out_path


_SILERO_MODEL = None
_SILERO_LOCK = threading.Lock()


def _silero_model():
    global _SILERO_MODEL
    if _SILERO_MODEL is not None:
        return _SILERO_MODEL
    import torch
    with _SILERO_LOCK:
        if _SILERO_MODEL is None:
            model_path = _voice_dir() / "v5_ru.pt"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            if not model_path.exists():
                torch.hub.download_url_to_file(SILERO_MODEL_URL, str(model_path), progress=False)
            model = torch.package.PackageImporter(str(model_path)).load_pickle("tts_models", "model")
            model.to(torch.device("cpu"))
            model.eval()
            _SILERO_MODEL = model
    return _SILERO_MODEL


def _run_silero(text: str, out_path: Path) -> Path:
    import wave
    import torch
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    model = _silero_model()
    speaker = os.environ.get("JARVIS_SILERO_VOICE", DEFAULT_SILERO_VOICE).strip().lower()
    allowed = {"aidar", "baya", "kseniya", "xenia", "eugene"}
    if speaker not in allowed:
        speaker = DEFAULT_SILERO_VOICE
    with torch.inference_mode():
        audio = model.apply_tts(text=text, speaker=speaker, sample_rate=48000)
    audio = audio.detach().cpu().clamp(-1, 1)
    pcm = (audio * 32767).short().numpy().tobytes()
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000); wav.writeframes(pcm)
    return out_path


def _run_windows_sapi(text: str, out_path: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("SAPI доступен только на Windows")
    ps = "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SetOutputToWaveFile('%s'); $s.Speak('%s'); $s.Dispose()" % (str(out_path).replace("'", "''"), text.replace("'", "''")[:500])
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=120, capture_output=True)
    return out_path


def available_engines() -> list[str]:
    engines = []
    try:
        import torch  # noqa: F401
        engines.append("silero")
    except Exception:
        pass
    if os.environ.get("JARVIS_PIPER") or _piper_dir().joinpath("ru_RU-dmitri-medium.onnx").exists():
        engines.append("piper")
    if sys.platform == "win32":
        engines.append("sapi")
    return engines


def current_engine() -> str:
    mode = os.environ.get("JARVIS_TTS", "auto").lower()
    if mode == "off": return "off"
    if mode == "auto":
        engines = available_engines()
        return engines[0] if engines else "off"
    return mode


def speak(text: str) -> Path:
    engine = current_engine()
    if engine == "off": raise RuntimeError("TTS отключён (JARVIS_TTS=off)")
    text = " ".join(text.split())[:1000]
    out = Path(tempfile.gettempdir()) / "jarvis_tts.wav"
    if engine == "silero": return _run_silero(text, out)
    if engine == "piper": return _run_piper(text, out)
    if engine == "sapi": return _run_windows_sapi(text, out)
    raise RuntimeError(f"Неизвестный TTS-движок: {engine}")


def speak_and_play(text: str) -> Path:
    """Synthesize and play audio; playback can be interrupted by `stop()`."""
    global _PLAYBACK_PROCESS
    try:
        path = speak(text)
    except Exception:
        if os.environ.get("JARVIS_TTS", "auto").lower() == "auto" and sys.platform == "win32":
            path = _run_windows_sapi(" ".join(text.split())[:500], Path(tempfile.gettempdir()) / "jarvis_tts.wav")
        else:
            raise
    if sys.platform == "win32":
        ps = "(New-Object Media.SoundPlayer '%s').PlaySync();" % str(path).replace("'", "''")
        process = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with _PLAYBACK_LOCK:
            _PLAYBACK_PROCESS = process
        try:
            process.wait(timeout=120)
        finally:
            with _PLAYBACK_LOCK:
                if _PLAYBACK_PROCESS is process:
                    _PLAYBACK_PROCESS = None
    return path
