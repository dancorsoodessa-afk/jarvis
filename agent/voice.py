"""Microphone input, VAD, double-clap activation and speech detection."""

import os
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable, Optional


def available() -> bool:
    try:
        import sounddevice  # noqa: F401
        import speech_recognition  # noqa: F401
        return True
    except ImportError:
        return False


def _recognize(frames: bytes, samplerate: int) -> str:
    import speech_recognition as sr
    fd, name = tempfile.mkstemp(prefix="jarvis_mic_", suffix=".wav")
    os.close(fd)
    path = Path(name)
    try:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(samplerate); wav.writeframes(frames)
        recognizer = sr.Recognizer()
        with sr.AudioFile(str(path)) as source:
            audio = recognizer.record(source)
        try:
            return recognizer.recognize_google(audio, language="ru-RU").strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            raise RuntimeError(f"Сервис распознавания речи недоступен: {exc}") from exc
    finally:
        try: path.unlink()
        except OSError: pass


def _rms(block) -> float:
    try:
        return float((block.astype("float32") ** 2).mean() ** 0.5)
    except Exception:
        return 0.0


def listen_for_double_clap(samplerate: int = 16000, timeout: float = 0.0,
                           min_gap: float = 0.12, max_gap: float = 0.85) -> bool:
    """Wait for two short acoustic transients; independent of the LLM/STT."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Голосовой ввод не установлен.") from exc
    block_seconds = 0.02
    blocksize = int(samplerate * block_seconds)
    deadline = time.monotonic() + timeout if timeout else None
    ambient = []; first = None
    with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", blocksize=blocksize) as stream:
        while deadline is None or time.monotonic() < deadline:
            data, _ = stream.read(blocksize)
            level = _rms(np.asarray(data[:, 0], dtype=np.int16))
            if len(ambient) < 15:
                ambient.append(level); continue
            noise = sum(ambient) / len(ambient)
            threshold = max(1800.0, noise * 5.0)
            now = time.monotonic()
            if level >= threshold:
                if first is None:
                    first = now
                else:
                    gap = now - first
                    if min_gap <= gap <= max_gap:
                        return True
                    first = now
            if first is not None and now - first > max_gap:
                first = None
    return False


def listen_for_phrase(samplerate: int = 16000, silence_seconds: float = 0.55,
                      max_seconds: float = 8.0, start_timeout: float = 30.0,
                      on_speech_start: Optional[Callable[[], None]] = None) -> str:
    """Wait for speech, record until silence, then transcribe it."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Голосовой ввод не установлен.") from exc
    block_seconds = 0.03; blocksize = int(samplerate * block_seconds)
    calibration_blocks = max(1, int(0.30 / block_seconds)); silence_blocks = max(1, int(silence_seconds / block_seconds))
    max_blocks = max(1, int(max_seconds / block_seconds)); timeout_blocks = max(1, int(start_timeout / block_seconds))
    chunks = []; speech_started = False; silent_count = 0; ambient = []
    try:
        with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", blocksize=blocksize) as stream:
            for index in range(timeout_blocks + max_blocks):
                data, overflowed = stream.read(blocksize)
                if overflowed: continue
                block = np.asarray(data[:, 0], dtype=np.int16).copy(); level = _rms(block)
                if not speech_started:
                    if index < calibration_blocks: ambient.append(level)
                    noise = (sum(ambient) / len(ambient)) if ambient else 250.0
                    if level >= max(500.0, noise * 2.8):
                        speech_started = True; chunks.append(block)
                        if on_speech_start:
                            try: on_speech_start()
                            except Exception: pass
                    if index >= timeout_blocks: return ""
                    continue
                chunks.append(block)
                noise = (sum(ambient) / len(ambient)) if ambient else 250.0
                silent_count = silent_count + 1 if level < max(500.0, noise * 2.2) else 0
                if len(chunks) >= 12 and silent_count >= silence_blocks: break
                if len(chunks) >= max_blocks: break
    except Exception as exc:
        raise RuntimeError(f"Не удалось открыть микрофон: {exc}") from exc
    if not speech_started or not chunks: return ""
    raw = np.concatenate(chunks).astype(np.int16)
    trim = min(len(raw), int(samplerate * silence_seconds))
    if trim and len(raw) > trim: raw = raw[:-trim]
    return _recognize(raw.tobytes(), samplerate)


def extract_wake_command(text: str, wake_words: tuple[str, ...] = ("джарвис", "jarvis")) -> Optional[str]:
    normalized = " ".join(text.lower().strip().split())
    for wake in wake_words:
        if wake in normalized: return normalized.split(wake, 1)[1].strip(" ,.!?;:-")
    return None


def listen_for_wake_and_command(on_speech_start: Optional[Callable[[], None]] = None, samplerate: int = 16000) -> str:
    while True:
        text = listen_for_phrase(samplerate=samplerate, on_speech_start=on_speech_start)
        if not text: continue
        command = extract_wake_command(text)
        if command is not None:
            if command: return command
            return listen_for_phrase(samplerate=samplerate, silence_seconds=0.55, max_seconds=8.0, start_timeout=10.0, on_speech_start=on_speech_start)


def record_and_transcribe(seconds: int = 7, samplerate: int = 16000) -> str:
    return listen_for_phrase(samplerate=samplerate, silence_seconds=0.55, max_seconds=max(2.0, min(float(seconds), 12.0)), start_timeout=5.0)
