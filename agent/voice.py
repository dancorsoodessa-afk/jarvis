"""Reliable desktop microphone activation for JARVIS.

Activation is two short claps followed by speech. The microphone threshold is
calibrated from ambient noise instead of using one fixed value, which makes the
same build work with different Windows microphones and input levels.
"""
from __future__ import annotations

import os
import tempfile
import time
import wave
from pathlib import Path

SAMPLE_RATE = 16_000
CLAP_BLOCK_MS = 40
CLAP_GAP_SECONDS = 0.9
CLAP_THRESHOLD_FLOOR = 0.055
SPEECH_MIN_SECONDS = 0.16


def available() -> bool:
    try:
        import numpy  # noqa: F401
        import sounddevice  # noqa: F401
        return True
    except ImportError:
        return False


def _rms(block) -> float:
    import numpy as np
    a = np.asarray(block, dtype="float32")
    if a.size == 0:
        return 0.0
    return float((a * a).mean() ** 0.5) / 32768.0


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
        engine = stt.current_engine()
        if engine == "off":
            raise RuntimeError(
                "Локальное распознавание речи не установлено. "
                "Установите faster-whisper или настройте whisper.cpp."
            )
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
    baseline = levels[max(0, int(len(levels) * 0.75) - 1)]
    return max(0.003, baseline)


def listen_for_phrase(
    samplerate: int = SAMPLE_RATE,
    silence_seconds: float = 0.45,
    max_seconds: float = 8.0,
    start_timeout: float = 1.5,
    on_speech_start=None,
) -> str:
    """Record one utterance using adaptive voice activity detection."""
    import numpy as np
    import sounddevice as sd

    block_size = max(160, int(samplerate * 0.04))
    silence_blocks = max(1, int(silence_seconds / 0.04))
    timeout_blocks = max(1, int(start_timeout / 0.04))
    max_blocks = max(1, int(max_seconds / 0.04))
    chunks = []
    started = False
    silent = 0
    spoken_blocks = 0

    try:
        with sd.InputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
            blocksize=block_size,
        ) as stream:
            noise = _calibrate(stream, 4, block_size)
            speech_threshold = max(0.012, noise * 2.4)
            end_threshold = max(0.009, noise * 1.5)

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
                            try:
                                on_speech_start()
                            except Exception:
                                pass
                    elif i >= timeout_blocks:
                        return ""
                    continue

                chunks.append(block)
                spoken_blocks += 1
                silent = silent + 1 if level < end_threshold else 0
                if spoken_blocks >= int(SPEECH_MIN_SECONDS / 0.04) and silent >= silence_blocks:
                    break
                if spoken_blocks >= max_blocks:
                    break
    except Exception as exc:
        raise RuntimeError(f"Не удалось открыть микрофон: {exc}") from exc

    if not started or len(chunks) < int(SPEECH_MIN_SECONDS / 0.04):
        return ""
    return _recognize(chunks, samplerate)


def _is_clap(level: float, noise: float) -> bool:
    return level >= max(CLAP_THRESHOLD_FLOOR, noise * 6.0)


def listen_for_double_clap_and_command(
    on_speech_start=None,
    samplerate: int = SAMPLE_RATE,
) -> str:
    """Wait for two claps, close the standby stream, then capture speech."""
    import sounddevice as sd

    block_size = max(160, int(samplerate * CLAP_BLOCK_MS / 1000))
    last_clap = 0.0
    ambient = []
    last_level = 0.0
    triggered = False

    try:
        with sd.InputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
            blocksize=block_size,
        ) as stream:
            noise = _calibrate(stream, 18, block_size)
            while True:
                data, overflow = stream.read(block_size)
                if overflow:
                    continue
                level = _rms(data[:, 0])
                ambient.append(level)
                if len(ambient) > 60:
                    ambient.pop(0)
                if len(ambient) >= 20:
                    sorted_levels = sorted(ambient)
                    noise = max(0.003, sorted_levels[int(len(sorted_levels) * 0.65)])

                now = time.monotonic()
                rising = level > last_level * 1.35
                if _is_clap(level, noise) and (rising or level > 0.09):
                    if now - last_clap <= CLAP_GAP_SECONDS:
                        triggered = True
                        break
                    last_clap = now
                elif last_clap and now - last_clap > CLAP_GAP_SECONDS:
                    last_clap = 0.0
                last_level = level
    except Exception as exc:
        raise RuntimeError(f"Не удалось открыть микрофон: {exc}") from exc

    # Important on Windows/WASAPI: do not open a second InputStream while the
    # standby stream still owns the microphone. The previous implementation
    # did exactly that and could make the agent stop hearing after activation.
    if triggered:
        return listen_for_phrase(
            samplerate=samplerate,
            silence_seconds=0.45,
            max_seconds=8.0,
            start_timeout=1.5,
            on_speech_start=on_speech_start,
        )
    return ""


def listen_for_wake_and_command(on_speech_start=None, samplerate: int = SAMPLE_RATE):
    return listen_for_double_clap_and_command(on_speech_start, samplerate)


def record_and_transcribe(seconds=10, samplerate: int = SAMPLE_RATE):
    return listen_for_phrase(
        samplerate=samplerate,
        max_seconds=min(float(seconds), 8.0),
        start_timeout=1.5,
    )
