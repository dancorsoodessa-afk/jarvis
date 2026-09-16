"""Lightweight text-to-speech for Windows JARVIS.

Windows SAPI is the default because it adds no large ML model to the EXE.
Silero and Piper remain optional for users who explicitly configure them.
"""

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

SILERO_MODEL_URL = "https://models.silero.ai/models/tts/ru/v5_ru.pt"
DEFAULT_SILERO_VOICE = "eugene"
DEFAULT_SAPI_LANGUAGE = "ru-RU"
_PLAYBACK_LOCK = threading.Lock()
_PLAYBACK_PROCESS = None


def _voice_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "JARVIS" / "voice"


def _piper_dir() -> Path:
    return Path(os.environ.get("JARVIS_HOME", ".")) / "voice"


def stop() -> None:
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
    voice = os.environ.get(
        "JARVIS_PIPER_VOICE",
        str(_piper_dir() / "ru_RU-dmitri-medium.onnx"),
    )
    if not Path(voice).exists():
        raise RuntimeError(f"Голос piper не найден: {voice}")
    with open(out_path, "wb") as wav:
        subprocess.run(
            [piper, "-m", voice, "-f", "-"],
            input=text.encode("utf-8"),
            stdout=wav,
            check=True,
            timeout=60,
        )
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
    if speaker not in {"aidar", "baya", "kseniya", "xenia", "eugene"}:
        speaker = DEFAULT_SILERO_VOICE
    with torch.inference_mode():
        audio = model.apply_tts(text=text, speaker=speaker, sample_rate=48000)
    audio = audio.detach().cpu().clamp(-1, 1)
    pcm = (audio * 32767).short().numpy().tobytes()
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(pcm)
    return out_path


def _run_windows_sapi(text: str, out_path: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("SAPI доступен только на Windows")
    voice_name = os.environ.get("JARVIS_SAPI_VOICE", "").strip()
    gender = os.environ.get("JARVIS_TTS_GENDER", "male").strip().lower()
    if gender not in {"male", "female", "any"}:
        gender = "male"
    ps = r'''
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$target = $env:JARVIS_SAPI_TARGET
$text = $env:JARVIS_SAPI_TEXT
$wanted = $env:JARVIS_SAPI_VOICE
$wantedGender = $env:JARVIS_TTS_GENDER
$voices = @($s.GetInstalledVoices())
$selected = $null
if ($wanted) {
  foreach ($v in $voices) {
    if ($v.VoiceInfo.Name -like "*$wanted*") { $selected = $v.VoiceInfo.Name; break }
  }
}
if (-not $selected -and $wantedGender -ne "any") {
  foreach ($v in $voices) {
    if ($v.VoiceInfo.Culture.Name -eq "ru-RU" -and $v.VoiceInfo.Gender.ToString().ToLower() -eq $wantedGender) {
      $selected = $v.VoiceInfo.Name; break
    }
  }
}
if (-not $selected) {
  foreach ($v in $voices) {
    if ($v.VoiceInfo.Culture.Name -eq "ru-RU") { $selected = $v.VoiceInfo.Name; break }
  }
}
if ($selected) { $s.SelectVoice($selected) }
$s.Rate = 0
$s.Volume = 100
$s.SetOutputToWaveFile($target)
$s.Speak($text)
$s.Dispose()
'''
    env = os.environ.copy()
    env["JARVIS_SAPI_TARGET"] = str(out_path)
    env["JARVIS_SAPI_TEXT"] = text[:1000]
    env["JARVIS_SAPI_VOICE"] = voice_name
    env["JARVIS_TTS_GENDER"] = gender
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=True,
        timeout=60,
        capture_output=True,
        env=env,
    )
    return out_path


def available_engines() -> list[str]:
    engines = []
    if sys.platform == "win32":
        engines.append("sapi")
    try:
        import torch  # noqa: F401
        engines.append("silero")
    except Exception:
        pass
    if os.environ.get("JARVIS_PIPER") or _piper_dir().joinpath("ru_RU-dmitri-medium.onnx").exists():
        engines.append("piper")
    return engines


def current_engine() -> str:
    mode = os.environ.get("JARVIS_TTS", "sapi").strip().lower()
    if mode == "auto":
        return "sapi" if sys.platform == "win32" else (available_engines()[0] if available_engines() else "off")
    if mode == "off":
        return "off"
    return mode


def set_gender(gender: str) -> str:
    """Set the preferred SAPI voice gender and return the normalized value."""
    value = str(gender).strip().lower()
    aliases = {"мужской": "male", "муж": "male", "male": "male",
               "женский": "female", "жен": "female", "female": "female",
               "любой": "any", "любой голос": "any", "any": "any"}
    value = aliases.get(value, value)
    if value not in {"male", "female", "any"}:
        raise ValueError("Допустимые варианты: мужской, женский или любой")
    os.environ["JARVIS_TTS_GENDER"] = value
    return value


def speak(text: str) -> Path:
    engine = current_engine()
    if engine == "off":
        raise RuntimeError("TTS отключён (JARVIS_TTS=off)")
    text = " ".join(text.split())[:1000]
    out = Path(tempfile.gettempdir()) / "jarvis_tts.wav"
    if engine == "sapi":
        return _run_windows_sapi(text, out)
    if engine == "silero":
        return _run_silero(text, out)
    if engine == "piper":
        return _run_piper(text, out)
    raise RuntimeError(f"Неизвестный TTS-движок: {engine}")


def speak_and_play(text: str) -> Path:
    global _PLAYBACK_PROCESS
    path = speak(text)
    if sys.platform == "win32":
        ps = "(New-Object Media.SoundPlayer '%s').PlaySync();" % str(path).replace("'", "''")
        process = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        with _PLAYBACK_LOCK:
            _PLAYBACK_PROCESS = process
        try:
            process.wait(timeout=120)
        finally:
            with _PLAYBACK_LOCK:
                if _PLAYBACK_PROCESS is process:
                    _PLAYBACK_PROCESS = None
    return path
