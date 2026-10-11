"""Голосовой цикл SUPERMAN: слово «Джарвис» активирует одну команду.

После ответа помощник снова ждёт ключевое слово. Нет хлопков и непрерывного
прослушивания команд без активации. Голосовой ввод запускается только при наличии сети.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from .logging_setup import get as get_log
from . import tts, voice

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
    """One wake word, one command, one response, then wait again."""

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

    def step(self, text: str):
        """Text adapter matching the one-activation/one-command voice contract."""
        text = " ".join(str(text).lower().split())
        if not text:
            return None

        if self.wake_enabled:
            command = self.strip_wake(text, self.wake_words)
            if command is None:
                return None
            if not command:
                self.active = False
                return "Слушаю. Скажите команду."
        else:
            command = text

        if self.is_stop(command):
            self.active = False
            return "Ожидаю."

        self.active = False
        result = self.agent.handle(command)
        return str(getattr(result, "text", result) or "").strip()

    def run(self):
        if not voice.available():
            raise RuntimeError("Голосовой ввод недоступен: установите sounddevice и numpy")

        self.log.info("SUPERMAN: голосовой режим; одно ключевое слово — одна команда")

        while True:
            try:
                command = self._wait_for_wake() if self.wake_enabled else self._listen()

                # Если пользователь произнёс только «Джарвис», принимаем следующую
                # реплику как одну команду, затем возвращаемся к ожиданию ключевого слова.
                if self.wake_enabled and not command:
                    tts.speak_and_play("Слушаю. Скажите команду.")
                    command = self._listen()

                if not command:
                    continue

                if self.is_stop(command):
                    tts.stop()
                    self.log.info("Голосовой режим: ожидание ключевого слова")
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
                time.sleep(0.5)
