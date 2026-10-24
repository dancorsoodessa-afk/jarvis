"""Cloud speech synthesis using Gemini TTS; no Windows system voice or third-party TTS provider."""
from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_PLAYBACK_LOCK = threading.Lock()
_PLAYBACK_ACTIVE = False
_PLAYBACK_TOKEN = 0
_PLAYBACK_PATH: Path | None = None

DEFAULT_TTS_MODEL = "gemini-3.8-flash-tts"
DEFAULT_TTS_VOICE = "Charon"
TTS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"


def _api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def available_engines() -> list[str]:
    return ["gemini"] if _api_key() else []


def current_engine() -> str:
    mode = os.environ.get("JARVIS_TTS", "gemini").strip().lower()
    if mode == "off":
        return "off"
    if mode not in {"auto", "gemini", "cloud"}:
        raise RuntimeError("JARVIS поддерживает облачную озвучку Gemini или режим off.")
    return "gemini" if _api_key() else "off"


def health_check(timeout: float | None = None) -> str:
    """Check the TTS model endpoint and credentials without generating audio."""
    if current_engine() == "off":
        raise RuntimeError("Для облачной озвучки нужен GEMINI_API_KEY.")
    model = (os.environ.get("JARVIS_TTS_MODEL") or DEFAULT_TTS_MODEL).strip()
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + urllib.parse.quote(model, safe="-._")
    request = urllib.request.Request(url, headers={"x-goog-api-key": _api_key(), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, min(20.0, float(timeout or 10.0)))) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict) or not body.get("name"):
            raise RuntimeError("Gemini TTS вернул неожиданный ответ проверки модели.")
        return "ONLINE"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Gemini TTS: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini TTS: сеть недоступна ({exc.reason}).") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Gemini TTS вернул некорректный JSON при проверке доступности.") from exc


def set_gender(gender: str) -> None:
    """Map the legacy gender toggle to Gemini's available voice profiles."""
    value = str(gender).strip().lower()
    if value in {"female", "женский"}:
        os.environ["JARVIS_TTS_VOICE"] = "Aoede"
    else:
        os.environ["JARVIS_TTS_VOICE"] = "Charon"


def _timeout() -> float:
    try:
        return max(5.0, min(120.0, float(os.environ.get("JARVIS_TTS_TIMEOUT", "45"))))
    except (TypeError, ValueError):
        return 45.0


def _generate_audio(text: str) -> bytes:
    key = _api_key()
    if not key:
        raise RuntimeError("Облачная озвучка требует GEMINI_API_KEY. Укажите ключ Gemini в Центре управления.")
    model = (os.environ.get("JARVIS_TTS_MODEL") or DEFAULT_TTS_MODEL).strip()
    voice = (os.environ.get("JARVIS_TTS_VOICE") or DEFAULT_TTS_VOICE).strip()
    payload = {
        "model": model,
        "input": [{
            "type": "user_input",
            "content": [{
                "type": "text",
                "text": text,
                "annotations": [{
                    "type": "speech_metadata",
                    "style": "Speak naturally and clearly in Russian, with a confident, calm assistant delivery.",
                }],
            }],
        }],
        "response_format": {"type": "audio", "mime_type": "audio/wav"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    request = urllib.request.Request(
        TTS_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=_timeout()) as response:
                result = json.loads(response.read().decode("utf-8"))
            # The SDK exposes output_audio, but the raw REST response stores audio
            # in steps[].content[].data. Accept both shapes defensively.
            audio = result.get("output_audio", {}).get("data", "")
            if not audio:
                for step in result.get("steps", []):
                    if not isinstance(step, dict) or step.get("type") != "model_output":
                        continue
                    for block in step.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "audio" and block.get("data"):
                            audio = block["data"]
            if not audio:
                raise RuntimeError("Gemini TTS не вернул аудиоданные. Проверьте доступность модели и ключ.")
            return base64.b64decode(audio, validate=True)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            if exc.code in retryable and attempt < 2:
                import time
                time.sleep(0.8 * (2 ** attempt))
                continue
            raise RuntimeError(f"Ошибка облачной озвучки Gemini: HTTP {exc.code}. {detail}") from exc
        except urllib.error.URLError as exc:
            if attempt < 2:
                import time
                time.sleep(0.8 * (2 ** attempt))
                continue
            raise RuntimeError(f"Не удалось подключиться к Gemini TTS: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("Gemini TTS вернул некорректный аудиоответ.") from exc
    raise RuntimeError("Gemini TTS временно недоступен после повторных попыток.")


def _write_audio(audio: bytes) -> Path:
    if not audio:
        raise RuntimeError("Gemini TTS вернул пустой аудиофайл.")
    fd, name = tempfile.mkstemp(prefix="jarvis_gemini_tts_", suffix=".wav")
    os.close(fd)
    path = Path(name)
    try:
        # Gemini Interactions API returns raw 24 kHz mono signed 16-bit PCM.
        # Accept a complete WAV too, in case the provider changes response framing.
        if audio[:4] == b"RIFF":
            path.write_bytes(audio)
        else:
            import wave
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(audio)
        with path.open("rb") as handle:
            if handle.read(4) != b"RIFF":
                raise RuntimeError("Не удалось сформировать WAV из ответа Gemini TTS.")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def speak(text: str) -> Path:
    text = " ".join(str(text).split())[:4000]
    if not text:
        raise RuntimeError("Пустой текст для озвучки.")
    if current_engine() != "gemini":
        raise RuntimeError("Облачная озвучка Gemini не настроена.")
    return _write_audio(_generate_audio(text))


def speak_and_play(text: str, on_playback_start=None):
    """Generate cloud audio, signal playback start, then play until it ends."""
    global _PLAYBACK_ACTIVE, _PLAYBACK_TOKEN, _PLAYBACK_PATH
    path = speak(text)
    stop()
    with _PLAYBACK_LOCK:
        _PLAYBACK_TOKEN += 1
        token = _PLAYBACK_TOKEN
        _PLAYBACK_ACTIVE = True
        _PLAYBACK_PATH = path
    try:
        if on_playback_start:
            on_playback_start()
        if os.name == "nt":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
        else:
            import wave
            import numpy as np
            import sounddevice as sd
            with wave.open(str(path), "rb") as wav:
                frames = wav.readframes(wav.getnframes())
                rate = wav.getframerate()
                channels = wav.getnchannels()
            audio = np.frombuffer(frames, dtype=np.int16)
            if channels > 1:
                audio = audio.reshape(-1, channels)
            sd.play(audio, rate, blocking=True)
    except Exception as exc:
        raise RuntimeError(f"Не удалось воспроизвести облачную речь: {exc}") from exc
    finally:
        with _PLAYBACK_LOCK:
            if _PLAYBACK_TOKEN == token:
                _PLAYBACK_ACTIVE = False
                _PLAYBACK_PATH = None
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def stop() -> None:
    global _PLAYBACK_ACTIVE, _PLAYBACK_TOKEN, _PLAYBACK_PATH
    with _PLAYBACK_LOCK:
        _PLAYBACK_TOKEN += 1
        path = _PLAYBACK_PATH
        _PLAYBACK_PATH = None
        _PLAYBACK_ACTIVE = False
    if os.name == "nt":
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
    try:
        if path:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def is_playing() -> bool:
    with _PLAYBACK_LOCK:
        return _PLAYBACK_ACTIVE
