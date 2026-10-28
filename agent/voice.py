"""Надёжный голосовой ввод JARVIS: локальная запись микрофона + облачный STT, без хлопков.

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
    """Return RMS amplitude normalized to the float audio range 0.0–1.0.

    InputStream is configured with dtype=int16, so divide the raw RMS by the
    full-scale int16 amplitude exactly once.
    """
    import numpy as np
    a = np.asarray(block, dtype=np.float32)
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


def _supported_capture_rate(sd, requested_rate: int, device) -> int:
    """Use the requested rate when supported; otherwise use the input device's default."""
    try:
        sd.check_input_settings(device=device, samplerate=requested_rate, channels=1, dtype="int16")
        return requested_rate
    except Exception as requested_error:
        try:
            info = sd.query_devices(device, "input")
            fallback = int(round(float(info.get("default_samplerate") or 0)))
            if fallback <= 0:
                raise RuntimeError("У микрофона не указан допустимый sample rate.")
            sd.check_input_settings(device=device, samplerate=fallback, channels=1, dtype="int16")
            return fallback
        except Exception as fallback_error:
            raise RuntimeError(
                f"Микрофон не поддерживает {requested_rate} Гц; "
                f"резервная частота ввода также недоступна: {fallback_error}"
            ) from requested_error


def _resample_frames(frames, source_rate: int, target_rate: int):
    """Resample concatenated mono int16 frames without an optional DSP dependency."""
    import numpy as np
    samples = np.concatenate(frames).astype(np.float32)
    if source_rate == target_rate or samples.size == 0:
        return [samples.astype(np.int16)]
    output_size = max(1, int(round(samples.size * target_rate / source_rate)))
    source_positions = np.arange(samples.size, dtype=np.float64)
    target_positions = np.arange(output_size, dtype=np.float64) * source_rate / target_rate
    target_positions = np.minimum(target_positions, max(0, samples.size - 1))
    converted = np.interp(target_positions, source_positions, samples)
    return [np.clip(np.rint(converted), -32768, 32767).astype(np.int16)]


def listen_for_phrase(
    samplerate: int = SAMPLE_RATE,
    silence_seconds: float = 0.55,
    max_seconds: float = 120.0,
    start_timeout: float = 4.0,
    on_speech_start=None,
    on_audio_level=None,
    should_stop=None,
    interrupt_guard=None,
) -> str:
    """Записать одну фразу автоматически по уровню речи и распознать её."""
    import numpy as np
    import sounddevice as sd

    target_samplerate = samplerate
    device = _device()
    capture_samplerate = _supported_capture_rate(sd, target_samplerate, device)
    block_size = max(160, int(capture_samplerate * BLOCK_SECONDS))
    silence_blocks = max(1, int(silence_seconds / BLOCK_SECONDS))
    timeout_blocks = max(0, int(start_timeout / BLOCK_SECONDS))
    max_blocks = max(1, int(max_seconds / BLOCK_SECONDS))
    chunks = []
    started = False
    silent = 0
    spoken_blocks = 0
    idle_blocks = 0
    onset_blocks = 0
    onset_frames = []
    # While TTS is playing, require a longer and louder onset to reduce
    # false interruptions caused by the speakers leaking into the microphone.

    try:
        with sd.InputStream(
            samplerate=capture_samplerate, channels=1, dtype="int16", blocksize=block_size,
            device=device, latency="low",
        ) as stream:
            noise = _calibrate(stream, 6, block_size)
            speech_threshold = max(0.006, noise * 1.8)
            end_threshold = max(0.004, noise * 1.15)
            # A zero start timeout means wait for speech, not "give up after one block".
            while True:
                if should_stop and should_stop():
                    return ""
                data, overflow = stream.read(block_size)
                if overflow:
                    continue
                block = np.asarray(data[:, 0], dtype=np.int16).copy()
                level = _rms(block)
                if on_audio_level:
                    try:
                        on_audio_level(level)
                    except Exception:
                        pass
                if not started:
                    idle_blocks += 1
                    playing = bool(interrupt_guard and interrupt_guard())
                    threshold = max(speech_threshold, 0.014 if playing else speech_threshold)
                    required_onset = 5 if playing else 2
                    if level >= threshold:
                        onset_blocks += 1
                        onset_frames.append(block)
                        if onset_blocks >= required_onset:
                            started = True
                            chunks.extend(onset_frames)
                            spoken_blocks = len(onset_frames)
                            if on_speech_start:
                                try:
                                    on_speech_start()
                                except Exception:
                                    pass
                            onset_frames.clear()
                    else:
                        onset_blocks = 0
                        onset_frames.clear()
                        if timeout_blocks and idle_blocks >= timeout_blocks:
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
    if capture_samplerate != target_samplerate:
        chunks = _resample_frames(chunks, capture_samplerate, target_samplerate)
    return _recognize(chunks, target_samplerate)



def listen_for_wake_and_command(on_speech_start=None, samplerate: int = SAMPLE_RATE):
    return listen_for_phrase(samplerate=samplerate, on_speech_start=on_speech_start)


def record_and_transcribe(seconds=8, samplerate: int = SAMPLE_RATE):
    return listen_for_phrase(samplerate=samplerate, max_seconds=float(seconds), start_timeout=3.0)
