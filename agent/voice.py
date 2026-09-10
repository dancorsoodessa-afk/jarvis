"""Microphone recording and speech recognition for the desktop UI.

Recording is local; recognition uses Google's public speech-recognition endpoint
through the SpeechRecognition package. No API key is stored for this feature.
"""

import os
import tempfile
import wave
from pathlib import Path


def available() -> bool:
    try:
        import sounddevice  # noqa: F401
        import speech_recognition  # noqa: F401
        return True
    except ImportError:
        return False


def record_and_transcribe(seconds: int = 7, samplerate: int = 16000) -> str:
    """Record from the default microphone and return recognized Russian text."""
    try:
        import sounddevice as sd
        import speech_recognition as sr
    except ImportError as exc:
        raise RuntimeError(
            "Голосовой ввод не установлен. Пересоберите JARVIS из актуальной ветки foundation."
        ) from exc

    try:
        frames = sd.rec(int(seconds * samplerate), samplerate=samplerate,
                        channels=1, dtype="int16")
        sd.wait()
    except Exception as exc:
        raise RuntimeError(f"Не удалось открыть микрофон: {exc}") from exc

    fd, name = tempfile.mkstemp(prefix="jarvis_mic_", suffix=".wav")
    os.close(fd)
    path = Path(name)
    try:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(samplerate)
            wav.writeframes(frames.tobytes())
        recognizer = sr.Recognizer()
        with sr.AudioFile(str(path)) as source:
            audio = recognizer.record(source)
        try:
            return recognizer.recognize_google(audio, language="ru-RU").strip()
        except sr.UnknownValueError:
            raise RuntimeError("Не удалось разобрать речь. Попробуйте говорить громче и ближе к микрофону.")
        except sr.RequestError as exc:
            raise RuntimeError(f"Сервис распознавания речи недоступен: {exc}") from exc
    finally:
        try:
            path.unlink()
        except OSError:
            pass
