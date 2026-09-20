"""Unified voice loop for JARVIS.

Desktop and CLI activate only after the wake word "Jarvis" is detected.
capture. The legacy ``step`` method remains for compatibility with existing
wake-word tests and integrations.
"""

import os
import time
from pathlib import Path

from .logging_setup import get as get_log
from . import stt, tts, voice

DEFAULT_WAKE_WORDS = ("джарвис", "jarvis")


class Recorder:
    """Legacy microphone recorder kept for compatibility."""

    def __init__(self, samplerate: int = 16000):
        self.samplerate = samplerate

    def record(self, out_path: Path) -> Path:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Микрофон недоступен: установите voice-зависимости") from exc
        chunk = int(0.1 * self.samplerate)
        frames = []
        silence = 0.0
        spoken = 0.0
        started = time.time()
        with sd.InputStream(samplerate=self.samplerate, channels=1, dtype="int16"):
            while time.time() - started < 12:
                data, _overflow = sd.rec(chunk, samplerate=self.samplerate, channels=1, dtype="int16")
                sd.wait()
                frames.append(data.copy())
                level = float(np.abs(data).mean()) / 32768.0
                if level > 0.01:
                    silence = 0.0
                    spoken += 0.1
                elif spoken > 0:
                    silence += 0.1
                    if silence >= 1.5:
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
    """Voice assistant loop activated only by the wake word "Jarvis"."""

    def __init__(self, agent, recorder: Recorder | None = None,
                 wake_words=None, wake_enabled: bool | None = None,
                 tmp_dir: str | None = None):
        self.agent = agent
        self.recorder = recorder or Recorder()
        env_wake = os.environ.get("JARVIS_WAKE")
        self.wake_enabled = (env_wake != "off") if wake_enabled is None else wake_enabled
        words = wake_words or tuple(os.environ.get("JARVIS_WAKE_WORD", "").lower().split() or DEFAULT_WAKE_WORDS)
        self.wake_words = words
        self.log = get_log("voice")
        self.tmp_dir = tmp_dir or os.environ.get("JARVIS_HOME", ".")

    def listen_once(self, recorder=None) -> str:
        rec = recorder or self.recorder
        wav = Path(self.tmp_dir) / "jarvis_mic.wav"
        rec.record(wav)
        try:
            text = stt.transcribe(str(wav))
            return text.strip()
        finally:
            try:
                wav.unlink()
            except OSError:
                pass

    @staticmethod
    def strip_wake(text: str, wake_words) -> str | None:
        low = " ".join(text.lower().split())
        for word in wake_words:
            if low.startswith(word):
                return low[len(word):].strip(" ,.!")
        return None

    def step(self, heard: str) -> str | None:
        if self.wake_enabled:
            command = self.strip_wake(heard, self.wake_words)
            if command is None:
                return None
            if not command:
                return "Слушаю."
        else:
            command = heard
        result = self.agent.handle(command)
        self.log.info("Голос: %r -> %r", command, result.text[:80])
        return result.text

    def run(self):
        """Continuously listen for speech, answer, then return to standby."""
        if not voice.available():
            raise RuntimeError("Голосовой ввод недоступен: установите sounddevice и numpy")
        self.log.info("Голосовой режим включён: ожидание речи")
        while True:
            try:
                heard = voice.listen_for_phrase(
                    silence_seconds=0.70,
                    max_seconds=10.0,
                    start_timeout=5.0,
                    on_speech_start=tts.stop,
                )
                if not heard:
                    continue
                command = self.strip_wake(heard, self.wake_words)
                if command is None:
                    continue
                if not command:
                    heard = voice.listen_for_phrase(
                        silence_seconds=0.70,
                        max_seconds=10.0,
                        start_timeout=5.0,
                        on_speech_start=tts.stop,
                    )
                    command = heard.strip() if heard else ""
                if not command:
                    continue
                result = self.agent.handle(command)
                answer = str(result.text or "").strip()
                self.log.info("Голос: %r -> %r", command, answer[:80])
                if answer:
                    tts.speak_and_play(answer)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self.log.warning("Ошибка голосового цикла: %s", exc, exc_info=True)
                time.sleep(1)
