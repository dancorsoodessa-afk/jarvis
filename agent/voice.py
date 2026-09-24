"""Надёжный локальный голосовой ввод JARVIS: VAD + faster-whisper, без хлопков.

Микрофон открывается на один цикл прослушивания, калибровка короткая,
порог адаптивный. Устройство можно задать через JARVIS_AUDIO_DEVICE.
"""
from __future__ import annotations

import os
import tempfile
import wave
from pathlib import Path

SAMPLE_RATE = 16_000
BLOCK_SECONDS = 0.04
SPEECH_MIN_SECONDS = 0.20


def available() -> bool:
    try:
        import numpy  # noqa: F401
        import sounddevice  # noqa: F401
        from . import stt
        return stt.current_engine() != "off"
    except Exception:
        return False


def audio_devices() -> list[str]:
    try:
        import sounddevice as sd
        return [str(d["name"]) for d in sd.query_devices() if int(d.get("max_input_channels", 0)) > 0]
    except Exception:
        return []


def _device():
    value = os.environ.get("JARVIS_AUDIO_DEVICE", "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _rms(block) -> float:
    import numpy as np
    a = np.asarray(block, dtype="float32")
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a * a))) / 32768.0


def _write_wav(frames, samplerate: int) -> Path:
    fd, name = tempfile.mkstemp(prefix="jarvis_mic_", suffix=".wav")
    os.close(fd)
    path = Path(name)
    import numpy as np
    raw = np.concatenate(frames).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(raw.tobytes())
    return path


def _recognize(frames, samplerate: int) -> str:
    path = _write_wav(frames, samplerate)
    try:
        from . import stt
        return stt.transcribe(str(path)).strip()
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _calibrate(stream, blocks: int, block_size: int) -> float:
    levels = []
    for _ in range(blocks):
        data, overflow = stream.read(block_size)
        if not overflow:
            levels.append(_rms(data[:, 0]))
    if not levels:
        return 0.008
    levels.sort()
    return max(0.0025, levels[max(0, int(len(levels) * 0.75) - 1)])


def listen_for_phrase(
    samplerate: int = SAMPLE_RATE,
    silence_seconds: float = 0.55,
    max_seconds: float = 120.0,
    start_timeout: float = 4.0,
    on_speech_start=None,
) -> str:
    """Записать одну фразу автоматически по уровню речи и распознать её."""
    import numpy as np
    import sounddevice as sd

    block_size = max(160, int(samplerate * BLOCK_SECONDS))
    silence_blocks = max(1, int(silence_seconds / BLOCK_SECONDS))
    timeout_blocks = max(1, int(start_timeout / BLOCK_SECONDS))
    max_blocks = max(1, int(max_seconds / BLOCK_SECONDS))
    chunks = []
    started = False
    silent = 0
    spoken_blocks = 0

    try:
        with sd.InputStream(
            samplerate=samplerate, channels=1, dtype="int16", blocksize=block_size,
            device=_device(), latency="low",
        ) as stream:
            noise = _calibrate(stream, 6, block_size)
            speech_threshold = max(0.006, noise * 1.8)
            end_threshold = max(0.004, noise * 1.15)
            for i in range(timeout_blocks + max_blocks):
                data, overflow = stream.read(block_size)
                if overflow:
                    continue
                block = np.asarray(data[:, 0], dtype=np.int16).copy()
                level = _rms(block)
                if not started:
                    if level >= speech_threshold:
                        started = True
                        chunks.append(block)
                        spoken_blocks = 1
                        if on_speech_start:
                            try: on_speech_start()
                            except Exception: pass
                    elif i >= timeout_blocks:
                        return ""
                    continue
                chunks.append(block)
                spoken_blocks += 1
                silent = silent + 1 if level < end_threshold else 0
                if spoken_blocks >= int(SPEECH_MIN_SECONDS / BLOCK_SECONDS) and silent >= silence_blocks:
                    break
                if spoken_blocks >= max_blocks:
                    break
    except Exception as exc:
        raise RuntimeError(f"Не удалось открыть микрофон: {exc}") from exc

    if not started or len(chunks) < int(SPEECH_MIN_SECONDS / BLOCK_SECONDS):
        return ""
    return _recognize(chunks, samplerate)



def listen_for_wake_and_command(on_speech_start=None, samplerate: int = SAMPLE_RATE):
    return listen_for_phrase(samplerate=samplerate, on_speech_start=on_speech_start)


def record_and_transcribe(seconds=8, samplerate: int = SAMPLE_RATE):
    return listen_for_phrase(samplerate=samplerate, max_seconds=min(float(seconds), 8.0), start_timeout=3.0)
