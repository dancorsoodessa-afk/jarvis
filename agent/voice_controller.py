"""Thread-safe JARVIS voice pipeline: one microphone owner, queued STT/TTS and recovery."""
from __future__ import annotations

import io
import logging
import os
import queue
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable

from . import stt, tts

SAMPLE_RATE = 16_000
BLOCK_SECONDS = 0.04
SILENCE_SECONDS = 0.65
MIN_SPEECH_SECONDS = 0.24
MAX_PHRASE_SECONDS = 12.0
_RECOVERY_DELAYS = (0.5, 1.0, 2.0, 4.0, 5.0)


def _logger() -> logging.Logger:
    log = logging.getLogger("jarvis.voice")
    if not log.handlers:
        try:
            path = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS" / "logs"
            path.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(path / "voice.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(handler)
            log.setLevel(logging.INFO)
        except OSError:
            logging.basicConfig(level=logging.INFO)
    return log


class UIBridge:
    """Thread-safe event bridge. Workers enqueue data; the GUI thread polls it."""

    def __init__(self, event_queue: queue.Queue):
        self._queue = event_queue

    def post(self, kind: str, *payload) -> None:
        self._queue.put((kind, *payload))


class MicLock:
    """Reject a second concurrent owner of the microphone."""

    def __init__(self):
        self._lock = threading.Lock()
        self._owner: str | None = None

    def acquire(self, owner: str) -> None:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError(f"Микрофон уже занят потоком {self._owner or 'unknown'}.")
        self._owner = owner

    def release(self) -> None:
        if self._lock.locked():
            self._owner = None
            self._lock.release()


class AudioCapture:
    """One InputStream owner; segment audio by silence and discard samples during TTS."""

    def __init__(
        self,
        mic_lock: MicLock,
        capture_blocked: Callable[[], bool],
        on_phrase: Callable[[bytes], None],
        on_level: Callable[[float], None],
        on_mic_status: Callable[[bool], None],
    ):
        self._mic_lock = mic_lock
        self._capture_blocked = capture_blocked
        self._on_phrase = on_phrase
        self._on_level = on_level
        self._on_mic_status = on_mic_status
        self._stop = threading.Event()
        self.mic_ok = False

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _wav(frames: list[bytes]) -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(b"".join(frames))
        return output.getvalue()

    def run(self) -> None:
        import numpy as np
        import sounddevice as sd

        block_size = int(SAMPLE_RATE * BLOCK_SECONDS)
        device_value = os.environ.get("JARVIS_AUDIO_DEVICE", "").strip()
        device = int(device_value) if device_value.isdigit() else (device_value or None)
        self._mic_lock.acquire("audio-capture")
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=block_size, device=device, latency="low",
            ) as stream:
                self.mic_ok = True
                self._on_mic_status(True)
                _logger().info("event=mic_open device=%s sample_rate=%s", device, SAMPLE_RATE)
                noise_levels: list[float] = []
                frames: list[bytes] = []
                started_at = 0.0
                last_voice_at = 0.0
                while not self._stop.is_set():
                    data, overflow = stream.read(block_size)
                    if overflow:
                        _logger().warning("event=mic_overflow")
                    block = np.asarray(data[:, 0], dtype=np.int16).copy()
                    level = float(np.sqrt(np.mean(block.astype("float32") ** 2))) / 32768.0
                    if not self._capture_blocked():
                        self._on_level(min(1.0, level * 12.0))
                    if self._capture_blocked():
                        frames.clear()
                        started_at = last_voice_at = 0.0
                        continue
                    now = time.monotonic()
                    if not frames and len(noise_levels) < 25:
                        noise_levels.append(level)
                    baseline = sorted(noise_levels)[len(noise_levels) // 2] if noise_levels else 0.0
                    threshold = max(0.006, baseline * 2.2)
                    if level >= threshold:
                        if not frames:
                            started_at = now
                        frames.append(block.tobytes())
                        last_voice_at = now
                    elif frames:
                        frames.append(block.tobytes())
                        if now - last_voice_at >= SILENCE_SECONDS:
                            duration = now - started_at
                            phrase = self._wav(frames)
                            frames = []
                            started_at = last_voice_at = 0.0
                            if duration >= MIN_SPEECH_SECONDS:
                                self._on_phrase(phrase)
                    if frames and now - started_at >= MAX_PHRASE_SECONDS:
                        phrase = self._wav(frames)
                        frames = []
                        started_at = last_voice_at = 0.0
                        self._on_phrase(phrase)
        finally:
            self.mic_ok = False
            self._on_mic_status(False)
            self._mic_lock.release()
            _logger().info("event=mic_closed")


class STTEngine:
    """STT adapter with final/error/end callbacks; cloud engine returns final-only text."""

    def __init__(self, on_partial=None, on_final=None, on_error=None, on_end=None):
        self.on_partial = on_partial or (lambda _text: None)
        self.on_final = on_final or (lambda _text: None)
        self.on_error = on_error or (lambda _error: None)
        self.on_end = on_end or (lambda: None)

    def transcribe(self, audio_path: str) -> str:
        try:
            text = stt.transcribe(audio_path).strip()
            self.on_final(text)
            return text
        except Exception as exc:
            self.on_error(exc)
            raise
        finally:
            self.on_end()


class TTSEngine:
    """Persistent serialized TTS queue; network synthesis/playback never blocks GUI."""

    def __init__(self, on_start, on_end, on_error):
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._shutdown = threading.Event()
        self._on_start = on_start
        self._on_end = on_end
        self._on_error = on_error
        self._thread = threading.Thread(target=self._run, name="jarvis-tts-worker", daemon=True)
        self._thread.start()

    def mark_thinking(self) -> None:
        """Move the state machine into LLM/tool processing."""
        self._set_state("THINKING")

    def complete_without_speech(self) -> None:
        """Finish a request when TTS is disabled."""
        self._set_state("LISTENING" if self._running and not self._stop.is_set() else "IDLE")

    def report_error(self, message: str) -> None:
        """Publish an error without blocking the caller or terminating the GUI."""
        threading.Thread(target=self._recover, args=(message,), name="jarvis-voice-recovery", daemon=True).start()

    def speak(self, text: str) -> None:
        self._queue.put(text)

    def stop(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        tts.stop()

    def shutdown(self) -> None:
        self.stop()
        self._shutdown.set()
        self._queue.put(None)

    def _run(self) -> None:
        while not self._shutdown.is_set():
            try:
                text = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if text is None:
                continue
            try:
                self._on_start()
                tts.speak_and_play(text, blocking=True)
            except Exception as exc:
                self._on_error(exc)
            finally:
                self._on_end()


class VoiceController:
    """Voice facade and state-machine owner. GUI only renders posted state events."""

    STATES = {"IDLE", "LISTENING", "UNDERSTANDING", "THINKING", "SPEAKING", "ERROR"}

    def __init__(self, ui: UIBridge, on_text: Callable[[str], None]):
        self.ui = ui
        self._on_text_callback = on_text
        self._lock = threading.RLock()
        self._running = False
        self._is_speaking = threading.Event()
        self._stop = threading.Event()
        self._stt_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=3)
        self._mic_lock = MicLock()
        self._capture: AudioCapture | None = None
        self._threads: list[threading.Thread] = []
        self._state = "IDLE"
        self._last_error = ""
        self._mic_ok = False
        self._log = _logger()
        self.stt_engine = STTEngine(
            on_partial=lambda text: self.ui.post("voice_partial", text),
            on_final=self.on_text,
            on_error=lambda exc: self._log.error("event=stt_error error=%s", exc),
            on_end=lambda: self._log.info("event=stt_end"),
        )
        self.tts_engine = TTSEngine(self._tts_started, self._tts_ended, self._tts_error)

    def _set_state(self, state: str, message: str = "") -> None:
        if state not in self.STATES:
            raise ValueError(f"Недопустимое состояние голоса: {state}")
        with self._lock:
            self._state = state
            if state == "ERROR" and message:
                self._last_error = message
        self._log.info("event=state state=%s message=%s", state, message[:300])
        self.ui.post("voice_state", state, message)

    def _capture_blocked(self) -> bool:
        with self._lock:
            return self._is_speaking.is_set() or self._state in {"UNDERSTANDING", "THINKING", "SPEAKING"}

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "last_error": self._last_error,
                "mic": "ok" if self._mic_ok else "fail",
                "running": self._running,
                "is_speaking": self._is_speaking.is_set(),
            }

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            alive = [thread.name for thread in self._threads if thread.is_alive()]
            if alive:
                raise RuntimeError("Предыдущий голосовой цикл ещё останавливается: " + ", ".join(alive))
            self._threads = []
            self._running = True
            self._stop.clear()
            self._stt_queue = queue.Queue(maxsize=3)
            self._threads = [
                threading.Thread(target=self._capture_worker, name="jarvis-audio-capture", daemon=True),
                threading.Thread(target=self._stt_worker, name="jarvis-stt-worker", daemon=True),
            ]
            for thread in self._threads:
                thread.start()
        self._set_state("LISTENING")
        self._log.info("event=start")

    def stop(self) -> None:
        with self._lock:
            was_running = self._running
            self._running = False
            self._stop.set()
            capture = self._capture
        if capture:
            capture.stop()
        if was_running:
            try:
                self._stt_queue.put_nowait(None)
            except queue.Full:
                pass
        self.tts_engine.stop()
        self._is_speaking.clear()
        self._set_state("IDLE")
        self._log.info("event=stop running=%s", was_running)

    def shutdown(self) -> None:
        self.stop()
        self.tts_engine.shutdown()
        self._log.info("event=shutdown")

    def on_text(self, final: str) -> None:
        text = " ".join(str(final or "").split())
        if not text:
            self._log.warning("event=empty_final")
            self.ui.post("voice_status", "Речь не распознана. Продолжаю слушать.")
            if self._running and not self._is_speaking.is_set():
                self._set_state("LISTENING")
            return
        normalized = text.lower().replace("ё", "е").strip(" .,!?")
        if normalized in {"стоп голос", "останови голос", "выключи голос"}:
            self.stop()
            self.ui.post("voice_status", "Голосовой режим остановлен.")
            return
        if normalized in {"статус голоса", "проверь голос", "состояние голоса"}:
            status = self.status()
            self.speak(
                f"Состояние голоса: {status['state']}. Микрофон: {status['mic']}. " +
                (f"Последняя ошибка: {status['last_error']}" if status["last_error"] else "Ошибок нет.")
            )
            return
        self._set_state("UNDERSTANDING")
        try:
            self._on_text_callback(text)
            if self._running:
                self._set_state("THINKING")
        except Exception as exc:
            self._log.exception("event=command_callback_error")
            self._recover(f"Не удалось передать команду: {exc}")

    def speak(self, text: str) -> None:
        value = " ".join(str(text or "").split())
        if not value:
            self._log.warning("event=empty_tts")
            return
        self._set_state("THINKING")
        self.tts_engine.speak(value)

    def _recover(self, message: str) -> None:
        self._set_state("ERROR", message)
        if self._running and not self._stop.wait(0.5):
            self._set_state("LISTENING")

    def _capture_worker(self) -> None:
        delay_index = 0
        while not self._stop.is_set():
            try:
                self._capture = AudioCapture(
                    self._mic_lock,
                    self._capture_blocked,
                    self._enqueue_phrase,
                    lambda level: self.ui.post("audio_level", level),
                    lambda ok: setattr(self, "_mic_ok", ok),
                )
                self._capture.run()
                if self._stop.is_set():
                    break
                raise RuntimeError("Поток микрофона неожиданно завершился.")
            except Exception as exc:
                self._mic_ok = False
                message = f"Микрофон недоступен: {exc}"
                self._log.exception("event=capture_error")
                self._set_state("ERROR", message)
                delay = _RECOVERY_DELAYS[min(delay_index, len(_RECOVERY_DELAYS) - 1)]
                delay_index = min(delay_index + 1, len(_RECOVERY_DELAYS) - 1)
                if self._stop.wait(delay):
                    break
                self._set_state("LISTENING", "Повторное подключение к микрофону.")
            finally:
                self._capture = None
        self._mic_ok = False

    def _enqueue_phrase(self, audio: bytes) -> None:
        try:
            self._stt_queue.put_nowait(audio)
            self._set_state("UNDERSTANDING")
        except queue.Full:
            self._log.warning("event=stt_queue_full dropped_audio=true")
            self.ui.post("voice_status", "Очередь распознавания занята; короткая фраза пропущена.")

    def _stt_worker(self) -> None:
        while not self._stop.is_set():
            try:
                audio = self._stt_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if audio is None:
                break
            if self._is_speaking.is_set():
                continue
            path = None
            try:
                with tempfile.NamedTemporaryFile(prefix="jarvis_stt_", suffix=".wav", delete=False) as handle:
                    path = Path(handle.name)
                    handle.write(audio)
                last_exc = None
                for attempt, delay in enumerate((0.0, 0.5, 1.0)):
                    if self._stop.is_set():
                        break
                    if delay and self._stop.wait(delay):
                        break
                    try:
                        self.stt_engine.transcribe(str(path))
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        self._log.error("event=stt_attempt_failed attempt=%s error=%s", attempt + 1, exc)
                if last_exc is not None:
                    self._recover(f"Ошибка распознавания после повторов: {last_exc}")
            except Exception as exc:
                self._log.exception("event=stt_worker_error")
                self._recover(f"Ошибка голосового контура: {exc}")
            finally:
                if path:
                    path.unlink(missing_ok=True)
                if self._running and not self._is_speaking.is_set() and self._state not in {"THINKING", "SPEAKING", "ERROR"}:
                    self._set_state("LISTENING")

    def _tts_started(self) -> None:
        self._is_speaking.set()
        self._set_state("SPEAKING")

    def _tts_ended(self) -> None:
        self._is_speaking.clear()
        if self._running and not self._stop.is_set():
            self._set_state("LISTENING")
        else:
            self._set_state("IDLE")

    def _tts_error(self, exc: Exception) -> None:
        self._log.error("event=tts_error error=%s", exc)
        self.ui.post("tts_error", str(exc))
        self._set_state("ERROR", str(exc))
