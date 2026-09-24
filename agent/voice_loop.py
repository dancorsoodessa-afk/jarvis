"""Непрерывный голосовой цикл JARVIS: одно пробуждение — дальше свободный диалог.

Без хлопков и без короткого лимита сессии. После слова «Джарвис» помощник
остаётся в активном режиме и принимает следующие реплики без повторного wake-word.
Команда выхода: «стоп», «режим ожидания», «спасибо, Джарвис».
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from .logging_setup import get as get_log
from . import stt, tts, voice

DEFAULT_WAKE_WORDS = ("джарвис", "jarvis")
STOP_PHRASES = (
    "стоп",
    "режим ожидания",
    "перейди в режим ожидания",
    "спасибо джарвис",
    "спасибо, джарвис",
)


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
            while time.time() - started < 120:
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
    """Continuous conversation after one wake word."""

    def __init__(self, agent, recorder: Recorder | None = None,
                 wake_words=None, wake_enabled: bool | None = None,
                 tmp_dir: str | None = None):
        self.agent = agent
        self.recorder = recorder or Recorder()
        env_wake = os.environ.get("JARVIS_WAKE")
        self.wake_enabled = (env_wake != "off") if wake_enabled is None else wake_enabled
        words = wake_words or tuple(
            os.environ.get("JARVIS_WAKE_WORD", "").lower().split() or DEFAULT_WAKE_WORDS
        )
        self.wake_words = words
        self.log = get_log("voice")
        self.tmp_dir = tmp_dir or os.environ.get("JARVIS_HOME", ".")
        self.active = False

    @staticmethod
    def strip_wake(text: str, wake_words) -> str | None:
        low = " ".join(text.lower().split())
        for word in wake_words:
            if low.startswith(word):
                return low[len(word):].strip(" ,.!")
        return None

    @staticmethod
    def is_stop(text: str) -> bool:
        normalized = " ".join(text.lower().replace(",", " ").split())
        return normalized in {p.replace(",", "") for p in STOP_PHRASES}

    def _listen(self, timeout: float = 0.0) -> str:
        # timeout=0 means no conversational timeout: wait indefinitely.
        return voice.listen_for_phrase(
            silence_seconds=0.55,
            max_seconds=float(os.environ.get("JARVIS_VOICE_UTTERANCE_MAX", "120")),
            start_timeout=timeout,
            on_speech_start=tts.stop,
        )

    def _wait_for_wake(self) -> str:
        while True:
            heard = self._listen(timeout=0.0)
            if not heard:
                continue
            command = self.strip_wake(heard, self.wake_words)
            if command is not None:
                return command

    def run(self):
        if not voice.available():
            raise RuntimeError("Голосовой ввод недоступен: установите sounddevice и numpy")

        self.log.info("Голосовой режим включён: без хлопков, непрерывный диалог")

        while True:
            try:
                command = self._wait_for_wake() if self.wake_enabled and not self.active else self._listen()

                if not command:
                    continue

                if self.is_stop(command):
                    self.active = False
                    tts.stop()
                    self.log.info("Голосовой режим: ожидание")
                    continue

                self.active = True
                result = self.agent.handle(command)
                answer = str(result.text or "").strip()
                self.log.info("Голос: %r -> %r", command, answer[:80])

                if answer:
                    # Playback is interruptible by the next speech-start callback.
                    tts.speak_and_play(answer)

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self.log.warning("Ошибка голосового цикла: %s", exc, exc_info=True)
                time.sleep(0.5)
