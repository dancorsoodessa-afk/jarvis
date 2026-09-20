"""Надёжный локальный STT JARVIS: Vosk, русский язык, без облака."""

from __future__ import annotations
import json, os, shutil, urllib.request, zipfile, sys, threading
from pathlib import Path

MODEL_NAME = "vosk-model-small-ru-0.22"
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
_MODEL = None
_LOCK = threading.Lock()

def model_dir() -> Path:
    override = os.environ.get("JARVIS_VOSK_MODEL", "").strip()
    if override: return Path(override)
    if getattr(sys, "frozen", False): return Path(sys._MEIPASS) / "stt_model"
    return Path(os.environ.get("APPDATA", Path.home())) / "JARVIS" / "stt_model"

def _ensure_model() -> Path:
    path = model_dir()
    if (path / "am").exists() and (path / "conf").exists(): return path
    vendor = Path(__file__).resolve().parent.parent / "vendor" / "stt_model"
    if (vendor / "am").exists() and (vendor / "conf").exists(): return vendor
    path.parent.mkdir(parents=True, exist_ok=True)
    archive = path.parent / f"{MODEL_NAME}.zip"
    tmp = path.parent / f"{MODEL_NAME}.download"
    urllib.request.urlretrieve(MODEL_URL, tmp)
    tmp.replace(archive)
    with zipfile.ZipFile(archive) as zf: zf.extractall(path.parent)
    extracted = path.parent / MODEL_NAME
    if extracted != path:
        if path.exists(): shutil.rmtree(path, ignore_errors=True)
        extracted.rename(path)
    try: archive.unlink()
    except OSError: pass
    return path

def available_engines() -> list[str]:
    try:
        import vosk
        return ["vosk"]
    except ImportError:
        return []

def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "vosk").strip().lower()
    return "off" if mode == "off" else ("vosk" if "vosk" in available_engines() else "off")

def _get_model():
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            _MODEL = Model(str(_ensure_model()))
    return _MODEL

def transcribe(audio_path: str) -> str:
    if current_engine() == "off": raise RuntimeError("STT Vosk не установлен.")
    path = Path(audio_path)
    if not path.exists(): raise ValueError(f"Файл не найден: {audio_path}")
    import wave
    from vosk import KaldiRecognizer
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise RuntimeError("STT требует моно WAV PCM 16-bit.")
        rec = KaldiRecognizer(_get_model(), wf.getframerate())
        chunks = []
        while True:
            data = wf.readframes(4000)
            if not data: break
            if rec.AcceptWaveform(data): chunks.append(json.loads(rec.Result()).get("text", ""))
        chunks.append(json.loads(rec.FinalResult()).get("text", ""))
    return " ".join(x for x in chunks if x).strip()
