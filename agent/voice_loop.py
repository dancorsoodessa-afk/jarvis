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
    """Единый непрерывный голосовой цикл для интерфейса и автономного запуска."""

    def __init__(
        self, agent, recorder: Recorder | None = None, wake_words=None,
        wake_enabled: bool | None = None, tmp_dir: str | None = None,
        stop_event=None, on_command=None, on_response=None, on_status=None,
        on_error=None, on_command_error=None, on_audio_level=None, on_playback_start=None,
        on_playback_done=None, execution_lock=None,
        speak_responses: bool = True,
    ):
        import threading

        self.agent = agent
        self.recorder = recorder or Recorder()
        env_wake = os.environ.get("JARVIS_WAKE")
        self.wake_enabled = (env_wake != "off") if wake_enabled is None else wake_enabled
        words = wake_words or tuple(
            os.environ.get("JARVIS_WAKE_WORD", "").lower().split() or DEFAULT_WAKE_WORDS
        )
        self.wake_words = tuple(str(word).lower() for word in words)
        self.log = get_log("voice")
        self.tmp_dir = tmp_dir or os.environ.get("JARVIS_HOME", ".")
        self.active = False
        self.stop_event = stop_event or threading.Event()
        self.on_command = on_command
        self.on_response = on_response
        self.on_status = on_status
        self.on_error = on_error
        self.on_command_error = on_command_error
        self.on_audio_level = on_audio_level
        self.on_playback_start = on_playback_start
        self.on_playback_done = on_playback_done
        self.execution_lock = execution_lock
        self.speak_responses = speak_responses

    @staticmethod
    def strip_wake(text: str, wake_words) -> str | None:
        low = " ".join(str(text or "").lower().split())
        for word in wake_words:
            word = str(word).lower()
            if low == word:
                return ""
            if low.startswith(word) and len(low) > len(word) and low[len(word)] in " ,.!?:;—-":
                return low[len(word):].strip(" ,.!?:;—-")
        return None

    @staticmethod
    def is_stop(text: str) -> bool:
        normalized = " ".join(str(text or "").lower().replace(",", " ").split())
        return normalized in {p.replace(",", "") for p in STOP_PHRASES}

    def _listen(self, timeout: float = 0.0) -> str:
        return voice.listen_for_phrase(
            silence_seconds=0.55,
            max_seconds=float(os.environ.get("JARVIS_VOICE_UTTERANCE_MAX", "120")),
            start_timeout=timeout,
            on_speech_start=tts.stop,
            on_audio_level=self.on_audio_level,
            should_stop=self.stop_event.is_set,
            interrupt_guard=tts.is_playing,
        )

    def _wait_for_wake(self) -> str:
        """Ждать слово пробуждения, пока цикл не остановлен."""
        while not self.stop_event.is_set():
            heard = self._listen(timeout=0.0)
            if heard and self.strip_wake(heard, self.wake_words) is not None:
                return heard
        return ""

    def _route_input(self, text: str) -> tuple[str | None, str | None]:
        """Преобразовать фразу в команду или ответ голосового режима."""
        normalized = " ".join(str(text or "").lower().split())
        if not normalized:
            return None, None

        # Remove the wake prefix in both standby and active modes. This makes
        # "Джарвис, стоп" and "Джарвис, открой браузер" behave consistently.
        wake_command = self.strip_wake(normalized, self.wake_words) if self.wake_enabled else None
        if wake_command is not None:
            normalized = wake_command
            if not normalized:
                self.active = True
                return None, "Слушаю."

        if self.is_stop(normalized):
            self.active = False
            return None, "Ожидаю."

        if self.wake_enabled and not self.active and wake_command is None:
            return None, None

        self.active = True
        return normalized, None

    def step(self, text: str):
        """Синхронный адаптер для тестов и текстовых вызовов."""
        command, response = self._route_input(text)
        if response is not None:
            return response
        if command is None:
            return None
        result = self.agent.handle(command)
        return str(getattr(result, "text", result) or "").strip()

    def _notify(self, callback, *args):
        if callback:
            try:
                callback(*args)
            except Exception:
                self.log.debug("Ошибка callback голосового цикла", exc_info=True)

    def _speak(self, text: str):
        enabled = self.speak_responses() if callable(self.speak_responses) else self.speak_responses
        if not text or not enabled:
            return
        try:
            if tts.current_engine() == "gemini":
                tts.speak_and_play(
                    text,
                    on_playback_start=lambda: self._notify(self.on_playback_start),
                    blocking=True,
                )
                self._notify(self.on_playback_done)
        except Exception as exc:
            self._notify(self.on_error, exc)
            self.log.warning("Ошибка TTS: %s", exc, exc_info=True)

    def run(self):
        """Listen continuously while a single worker processes queued commands.

        The microphone remains available during AI requests. Commands spoken
        while the previous request is running are queued and processed in order.
        TTS playback is serialized; speech onset interrupts the current playback.
        """
        import queue
        import threading

        if not voice.available():
            raise RuntimeError("Голосовой ввод недоступен: установите sounddevice и numpy")

        self.log.info("Голосовой режим включён: очередь команд и непрерывное прослушивание")
        commands = queue.Queue()
        sentinel = object()

        def process_commands():
            while True:
                item = commands.get()
                try:
                    if item is sentinel:
                        return
                    kind, value = item
                    if kind == "command":
                        try:
                            if self.execution_lock is None:
                                result = self.agent.handle(value)
                            else:
                                with self.execution_lock:
                                    result = self.agent.handle(value)
                            answer = str(getattr(result, "text", result) or "").strip()
                            self.log.info("Голос: %r -> %r", value, answer[:80])
                            self._notify(self.on_response, answer)
                        except Exception as exc:
                            self._notify(self.on_command_error, exc)
                            self.log.warning("Ошибка обработки голосовой команды %r: %s", value, exc, exc_info=True)
                            continue
                    else:
                        answer = value

                    # Do not overlap two replies. A new user utterance interrupts
                    # current playback through voice.listen_for_phrase/on_speech_start.
                    while tts.is_playing() and not self.stop_event.is_set():
                        self.stop_event.wait(0.05)
                    if not self.stop_event.is_set():
                        self._speak(answer)
                finally:
                    commands.task_done()

        worker = threading.Thread(
            target=process_commands,
            name="jarvis-voice-command-worker",
            daemon=True,
        )
        worker.start()
        try:
            while not self.stop_event.is_set():
                heard = self._wait_for_wake() if self.wake_enabled and not self.active else self._listen()
                if self.stop_event.is_set():
                    break
                command, response = self._route_input(heard)

                if response is not None:
                    self._notify(self.on_status, response)
                    if response == "Ожидаю.":
                        tts.stop()
                        self.log.info("Голосовой режим: ожидание")
                    commands.put(("response", response))
                    continue

                if command is None:
                    continue

                self._notify(self.on_command, command)
                commands.put(("command", command))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self._notify(self.on_error, exc)
            self.log.warning("Ошибка голосового цикла: %s", exc, exc_info=True)
            raise
        finally:
            commands.put(sentinel)
            # Drain accepted commands before exiting; this prevents the UI
            # from losing commands already recognized and queued.
            commands.join()
            worker.join(timeout=2.0)
