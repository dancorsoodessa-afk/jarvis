"""Continuous voice mode for Jarvis: hear -> think -> speak.

Opt-in per the project performance rule:
  - JARVIS_VOICE=1 (or `python -m agent --voice`) to enable
  - STT engine must be configured (JARVIS_STT, see agent/stt.py)
  - TTS engine must be configured (JARVIS_TTS, see agent/tts.py)

Loop:
  1. Record microphone audio (bounded: max seconds + silence detection).
  2. Transcribe it (whisper.cpp / faster-whisper).
  3. Wake word gate: without "джарвис"/"jarvis" the phrase is ignored
     (unless wake gate is disabled via JARVIS_WAKE=off).
  4. agent.handle(text) -> answer, spoken aloud via TTS.

Mic recording uses `sounddevice` if installed; otherwise a RuntimeError
explains how to enable it. Everything is injectable for tests.
"""

import os
import time
from pathlib import Path

from .logging_setup import get as get_log
from . import stt, tts

DEFAULT_WAKE_WORDS = ("джарвис", "jarvis")
SILENCE_SECONDS = 1.5
MAX_RECORD_SECONDS = 12
SAMPLE_RATE = 16000


class Recorder:
    """Microphone capture -> wav file. Requires the optional `sounddevice`
    package plus numpy."""

    def __init__(self, samplerate: int = SAMPLE_RATE):
        self.samplerate = samplerate

    def record(self, out_path: Path) -> Path:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Микрофон недоступен: установите sounddevice "
                "(poetry add sounddevice) и numpy") from exc
        chunk = int(0.1 * self.samplerate)
        threshold = 0.01

        frames = []
        silence = 0.0
        spoken = 0.0
        started = time.time()
        stream = sd.InputStream(samplerate=self.samplerate,
                                channels=1, dtype="int16")
        with stream:
            while time.time() - started < MAX_RECORD_SECONDS:
                data, _overflow = sd.rec(chunk, samplerate=self.samplerate,
                                         channels=1, dtype="int16")
                sd.wait()
                frames.append(data.copy())
                level = float(np.abs(data).mean()) / 32768.0
                if level > threshold:
                    silence = 0.0
                    spoken += 0.1
                elif spoken > 0:
                    silence += 0.1
                    if silence >= SILENCE_SECONDS:
                        break
        if spoken < 0.3:
            raise RuntimeError("Речь не обнаружена")
        import wave
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.samplerate)
            wav.writeframes(b"".join(f.tobytes() for f in frames))
        return out_path


class VoiceLoop:
    """Wake-word gated voice assistant loop. Dependencies are injectable."""

    def __init__(self, agent, recorder: Recorder | None = None,
                 wake_words=None, wake_enabled: bool | None = None,
                 tmp_dir: str | None = None):
        self.agent = agent
        self.recorder = recorder or Recorder()
        env_wake = os.environ.get("JARVIS_WAKE")
        self.wake_enabled = (env_wake != "off") if wake_enabled is None \
            else wake_enabled
        words = wake_words or tuple(
            os.environ.get("JARVIS_WAKE_WORD", "").lower().split()
            or DEFAULT_WAKE_WORDS)
        self.wake_words = words
        self.log = get_log("voice")
        self.tmp_dir = tmp_dir or os.environ.get("JARVIS_HOME", ".")

    # -- pieces -----------------------------------------------------------

    def listen_once(self, recorder=None) -> str:
        """Record mic audio and transcribe. Raises RuntimeError on failure."""
        rec = recorder or self.recorder
        wav = Path(self.tmp_dir) / "jarvis_mic.wav"
        rec.record(wav)
        text = stt.transcribe(str(wav))
        try:
            wav.unlink()
        except OSError:
            pass
        return text.strip()

    @staticmethod
    def strip_wake(text: str, wake_words) -> str | None:
        """Return the command after the wake word, or None if absent."""
        low = " ".join(text.lower().split())
        for word in wake_words:
            if low.startswith(word):
                return low[len(word):].strip(" ,.!")
        return None

    def step(self, heard: str) -> str | None:
        """Process one transcribed phrase. Returns the spoken answer or None."""
        if self.wake_enabled:
            command = self.strip_wake(heard, self.wake_words)
            if command is None:
                return None
            if not command:
                return "Слушаю."  # wake word alone -> acknowledge
        else:
            command = heard
        result = self.agent.handle(command)
        self.log.info("Голос: %r -> %r", command, result.text[:80])
        return result.text

    def run(self):
        """Main loop. Ctrl+C to stop."""
        self.log.info("Голосовой режим включён (wake=%s)",
                      self.wake_words if self.wake_enabled else "off")
        while True:
            try:
                heard = self.listen_once()
            except RuntimeError as exc:
                print(f"[voice] {exc}")
                time.sleep(2)
                continue
            if not heard:
                continue
            try:
                answer = self.step(heard)
            except Exception:
                self.log.warning("Ошибка обработки фразы", exc_info=True)
                continue
            if answer:
                try:
                    tts.speak_and_play(answer)
                except (RuntimeError, OSError) as exc:
                    print(f"[voice] TTS: {exc}")
