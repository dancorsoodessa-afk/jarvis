"""JARVIS voice pipeline: single microphone owner, queued STT/TTS and explicit state machine."""
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
RECOVERY_DELAYS = (0.5, 1.0, 2.0, 4.0, 5.0)


def _supported_capture_rate(sd, device, requested_rate: int = SAMPLE_RATE) -> int:
    """Choose 16 kHz when supported, otherwise use the input device's native rate."""
    try:
        sd.check_input_settings(device=device, samplerate=requested_rate, channels=1, dtype="int16")
        return requested_rate
    except Exception as requested_error:
        try:
            info = sd.query_devices(device, "input")
            fallback = int(round(float(info.get("default_samplerate") or 0)))
            if fallback <= 0:
                raise RuntimeError("У микрофона не указана частота дискретизации.")
            sd.check_input_settings(device=device, samplerate=fallback, channels=1, dtype="int16")
            return fallback
        except Exception as fallback_error:
            raise RuntimeError(
                f"Микрофон не поддерживает {requested_rate} Гц; "
                f"резервная частота ввода также недоступна: {fallback_error}"
            ) from requested_error


def _resample_pcm16(frames: list[bytes], source_rate: int, target_rate: int = SAMPLE_RATE) -> bytes:
    """Resample mono signed 16-bit PCM frames to the STT target sample rate."""
    import numpy as np

    samples = np.frombuffer(b"".join(frames), dtype=np.int16)
    if samples.size == 0 or source_rate == target_rate:
        return samples.tobytes()
    output_size = max(1, int(round(samples.size * target_rate / source_rate)))
    source_positions = np.arange(samples.size, dtype=np.float64)
    target_positions = np.arange(output_size, dtype=np.float64) * source_rate / target_rate
    target_positions = np.minimum(target_positions, samples.size - 1)
    converted = np.interp(target_positions, source_positions, samples.astype(np.float32))
    return np.clip(np.rint(converted), -32768, 32767).astype(np.int16).tobytes()


def _logger() -> logging.Logger:
    logger = logging.getLogger("jarvis.voice")
    if not logger.handlers:
        try:
            folder = Path(os.environ.get("APPDATA", str(Path.home()))) / "JARVIS" / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(folder / "voice.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        except OSError:
            logging.basicConfig(level=logging.INFO)
    return logger


class UIBridge:
    """Workers publish immutable events; only the GUI main thread consumes them."""

    def __init__(self, event_queue: queue.Queue):
        self._queue = event_queue

    def post(self, kind: str, *payload) -> None:
        self._queue.put((kind, *payload))


class MicLock:
    """Process-local guard against accidentally opening two input streams."""

    def __init__(self):
        self._lock = threading.Lock()
        self._owner = ""

    def acquire(self, owner: str) -> None:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError(f"Микрофон занят и уже открыт: {self._owner or 'другой поток'}.")
        self._owner = owner

    def release(self) -> None:
        if self._lock.locked():
            self._owner = ""
            self._lock.release()


class AudioCapture:
    """Own exactly one sounddevice InputStream and split speech on trailing silence."""

    def __init__(
        self,
        mic_lock: MicLock,
        stop_event: threading.Event,
        capture_blocked: Callable[[], bool],
        on_phrase: Callable[[bytes], None],
        on_level: Callable[[float], None],
        on_mic_status: Callable[[bool], None],
    ):
        self._mic_lock = mic_lock
        self._stop = stop_event
        self._capture_blocked = capture_blocked
        self._on_phrase = on_phrase
        self._on_level = on_level
        self._on_mic_status = on_mic_status

    @staticmethod
    def _wav(frames: list[bytes], source_rate: int = SAMPLE_RATE) -> bytes:
        stream = io.BytesIO()
        pcm = _resample_pcm16(frames, source_rate, SAMPLE_RATE)
        with wave.open(stream, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(pcm)
        return stream.getvalue()

    def run(self) -> None:
        import numpy as np
        import sounddevice as sd

        device_value = os.environ.get("JARVIS_AUDIO_DEVICE", "").strip()
        device = int(device_value) if device_value.isdigit() else (device_value or None)
        acquired = False
        try:
            self._mic_lock.acquire("jarvis-audio-capture")
            acquired = True
            capture_rate = _supported_capture_rate(sd, device, SAMPLE_RATE)
            block_size = max(160, int(capture_rate * BLOCK_SECONDS))
            with sd.InputStream(
                samplerate=capture_rate, channels=1, dtype="int16",
                blocksize=block_size, device=device, latency="low",
            ) as stream:
                _logger().info("event=mic_open device=%s capture_rate=%s stt_rate=%s", device, capture_rate, SAMPLE_RATE)
                # Calibrate before declaring LISTENING so the first phrase is not used as noise.
                noise: list[float] = []
                for _ in range(12):
                    if self._stop.is_set():
                        return
                    calibration, overflowed = stream.read(block_size)
                    if not overflowed:
                        calibration_samples = np.asarray(calibration[:, 0], dtype=np.int16)
                        noise.append(float(np.sqrt(np.mean(calibration_samples.astype("float32") ** 2))) / 32768.0)
                self._on_mic_status(True)
                frames: list[bytes] = []
                started = last_voice = 0.0
                while not self._stop.is_set():
                    data, overflowed = stream.read(block_size)
                    if overflowed:
                        _logger().warning("event=mic_overflow")
                    samples = np.asarray(data[:, 0], dtype=np.int16).copy()
                    level = float(np.sqrt(np.mean(samples.astype("float32") ** 2))) / 32768.0
                    blocked = self._capture_blocked()
                    if not blocked:
                        self._on_level(min(1.0, level * 12.0))
                    if blocked:
                        frames.clear()
                        started = last_voice = 0.0
                        continue

                    now = time.monotonic()
                    baseline = sorted(noise)[len(noise) // 2] if noise else 0.0
                    threshold = max(0.0025, min(0.015, baseline * 2.5 + 0.001))
                    if level >= threshold:
                        if not frames:
                            started = now
                        frames.append(samples.tobytes())
                        last_voice = now
                    elif frames:
                        frames.append(samples.tobytes())
                        if now - last_voice >= SILENCE_SECONDS:
                            duration = now - started
                            phrase = self._wav(frames, capture_rate)
                            frames = []
                            started = last_voice = 0.0
                            if duration >= MIN_SPEECH_SECONDS and not self._stop.is_set():
                                self._on_phrase(phrase)
                    if frames and now - started >= MAX_PHRASE_SECONDS:
                        phrase = self._wav(frames)
                        frames = []
                        started = last_voice = 0.0
                        if not self._stop.is_set():
                            self._on_phrase(phrase)
        finally:
            self._on_mic_status(False)
            if acquired:
                self._mic_lock.release()
            _logger().info("event=mic_closed")


class STTEngine:
    """One final transcript per audio segment; failures are surfaced, never swallowed."""

    def __init__(self, on_partial=None, on_final=None, on_error=None, on_end=None):
        self.on_partial = on_partial or (lambda _text: None)
        self.on_final = on_final or (lambda _text: None)
        self.on_error = on_error or (lambda _error: None)
        self.on_end = on_end or (lambda: None)

    def transcribe_bytes(self, audio: bytes) -> str:
        path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="jarvis_stt_", suffix=".wav", delete=False) as file:
                path = Path(file.name)
                file.write(audio)
            transcript = str(stt.transcribe(str(path)) or "").strip()
            self.on_final(transcript)
            return transcript
        except Exception as exc:
            self.on_error(exc)
            raise
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
            self.on_end()


class TTSEngine:
    """Single persistent worker serializes synthesis and playback outside the GUI thread."""

    def __init__(self, on_start, on_end, on_error):
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._shutdown = threading.Event()
        self._active = threading.Event()
        self._current_cancel: threading.Event | None = None
        self._lock = threading.Lock()
        self._on_start = on_start
        self._on_end = on_end
        self._on_error = on_error
        self._thread = threading.Thread(target=self._run, name="jarvis-tts-worker", daemon=True)
        self._thread.start()

    def speak(self, text: str) -> None:
        if not self._shutdown.is_set():
            self._queue.put(text)

    def has_pending(self) -> bool:
        return not self._queue.empty() or self._active.is_set()

    def stop(self) -> None:
        with self._lock:
            if self._current_cancel is not None:
                self._current_cancel.set()
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
            cancel_event = threading.Event()
            with self._lock:
                self._current_cancel = cancel_event
            succeeded = True
            try:
                self._active.set()
                tts.speak_and_play(text, on_playback_start=self._on_start, blocking=True, cancel_event=cancel_event)
            except Exception as exc:
                succeeded = False
                self._on_error(exc)
            finally:
                self._active.clear()
                with self._lock:
                    if self._current_cancel is cancel_event:
                        self._current_cancel = None
                self._on_end(succeeded)


class VoiceController:
    """Only owner of voice state. start/stop are race-safe; GUI is event-queue-only."""

    STATES = {"IDLE", "LISTENING", "UNDERSTANDING", "THINKING", "SPEAKING", "DEGRADED", "ERROR"}

    def __init__(self, ui: UIBridge, on_text: Callable[[str], None]):
        self.ui = ui
        self._route_text = on_text
        self._lock = threading.RLock()
        self._running = False
        self._shutdown = False
        self._state = "IDLE"
        self._last_error = ""
        self._mic_ok = False
        self._quota_exceeded = False
        self._tts_off = False
        self._is_speaking = threading.Event()
        self._mic_lock = MicLock()
        self._capture_thread: threading.Thread | None = None
        self._capture_stop: threading.Event | None = None
        self._restart_after_capture = False
        self._stt_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
        self._log = _logger()
        self.stt_engine = STTEngine(
            on_partial=lambda text: self.ui.post("voice_partial", text),
            on_final=self.on_text,
            on_error=lambda exc: self._log.error("event=stt_error error=%s", exc),
            on_end=lambda: self._log.info("event=stt_end"),
        )
        self.tts_engine = TTSEngine(self._tts_started, self._tts_ended, self._tts_error)
        self._stt_thread = threading.Thread(target=self._stt_worker, name="jarvis-stt-worker", daemon=True)
        self._stt_thread.start()

    def _set_state(self, state: str, message: str = "") -> None:
        if state not in self.STATES:
            raise ValueError(f"Недопустимое состояние голоса: {state}")
        with self._lock:
            self._state = state
            if state in {"ERROR", "DEGRADED"} and message:
                self._last_error = message
        self._log.info("event=state state=%s message=%s", state, message[:300])
        self.ui.post("voice_state", state, message)

    def _capture_blocked(self) -> bool:
        with self._lock:
            return self._is_speaking.is_set() or self._state in {"UNDERSTANDING", "THINKING", "SPEAKING"}

    def status(self) -> dict:
        with self._lock:
            state = self._state
            last_error = self._last_error
            mic_ok = self._mic_ok
            running = self._running
        quota = stt.quota_exceeded()
        engine = stt.current_engine()
        if quota and state in {"IDLE", "LISTENING"}:
            state = "DEGRADED"
        tools_enabled = os.environ.get("GEMINI_TOOLS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        model = (os.environ.get("GEMINI_MODEL") or os.environ.get("JARVIS_CHAT_MODEL") or os.environ.get("GEMINI_STT_MODEL") or "не выбрана").strip()
        try:
            cloud_voice_available = engine in {"gemini", "groq"} and tts.current_engine() == "gemini" and not self._tts_off
        except Exception as exc:
            self._log.warning("event=voice_availability_check_failed error=%s", exc)
            cloud_voice_available = False
        return {
            "state": state,
            "last_error": last_error,
            "mic": "ok" if mic_ok else "fail",
            "mic_status": "mic ok" if mic_ok else "mic fail",
            "cloud_stt_status": ("cloud stt reserve: Groq" if engine == "groq" else "cloud stt off" if engine == "off" else "cloud stt on"),
            "tts_status": "tts off" if tts.current_engine() == "off" or self._tts_off else "tts on",
            "cloud_voice_available": cloud_voice_available,
            "quota_exceeded": quota,
            "quota_status": "yes" if quota else "no",
            "model": model,
            "tools_enabled": tools_enabled,
            "tools_status": "yes" if tools_enabled else "no (safe mode)",
            "cloud_stt": "groq" if engine == "groq" else "off" if engine == "off" else "on",
            "tts": "off" if tts.current_engine() == "off" or self._tts_off else "on",
            "running": running,
            "is_speaking": self._is_speaking.is_set(),
        }

    def start(self) -> None:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Голосовой контроллер уже завершён.")
            if self._running:
                return
            self._running = True
            if self._capture_thread is not None and self._capture_thread.is_alive():
                # Do not clear the old session's stop event; let it release the device first.
                self._restart_after_capture = True
                self.ui.post("voice_status", "Перезапускаю микрофон после освобождения предыдущего потока.")
                return
            self._launch_capture_locked()
        self._log.info("event=start")

    def _launch_capture_locked(self) -> None:
        stop_event = threading.Event()
        self._capture_stop = stop_event
        self._restart_after_capture = False
        worker = threading.Thread(
            target=self._capture_worker, args=(stop_event,),
            name="jarvis-audio-capture", daemon=True,
        )
        self._capture_thread = worker
        worker.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._restart_after_capture = False
            stop_event = self._capture_stop
            if stop_event is not None:
                stop_event.set()
        self._clear_stt_queue()
        self.tts_engine.stop()
        self._is_speaking.clear()
        self._set_state("IDLE")
        self._log.info("event=stop")

    def shutdown(self) -> None:
        self.stop()
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        self._stt_queue.put(None)
        self.tts_engine.shutdown()
        self._log.info("event=shutdown")

    def _clear_stt_queue(self) -> None:
        while True:
            try:
                self._stt_queue.get_nowait()
            except queue.Empty:
                return

    def mark_thinking(self) -> None:
        self._set_state("THINKING")

    def complete_without_speech(self) -> None:
        with self._lock:
            running = self._running
        self._set_state("LISTENING" if running else "IDLE")

    def report_error(self, message: str) -> None:
        threading.Thread(
            target=self._recover, args=(str(message),),
            name="jarvis-voice-recovery", daemon=True,
        ).start()

    def on_text(self, final: str) -> None:
        text = " ".join(str(final or "").split())
        if not text:
            self._log.warning("event=empty_final")
            self.ui.post("voice_status", "Речь не распознана. Продолжаю слушать.")
            with self._lock:
                running = self._running
            if running:
                self._set_state("LISTENING")
            return

        normalized = text.lower().replace("ё", "е").strip(" .,!?")
        if normalized in {"стоп голос", "останови голос", "выключи голос"}:
            self.stop()
            self.ui.post("voice_status", "Голосовой режим остановлен.")
            return
        if normalized in {"статус голоса", "проверь голос", "состояние голоса"}:
            state = self.status()
            report = (
                f"Состояние голоса: {state['state']}. Микрофон: {state['mic']}. "
                f"STT: {state['cloud_stt_status']}. TTS: {state['tts_status']}. "
                f"Модель: {state['model']}. Квота исчерпана: {state['quota_status']}. "
                f"Tools включены: {state['tools_status']}. "
                + (f"Последняя ошибка: {state['last_error']}" if state["last_error"] else "Последняя ошибка отсутствует.")
            )
            self.ui.post("voice_status", report)
            self.speak(report)
            return

        self._set_state("UNDERSTANDING")
        try:
            # The router callback must be quick and thread-safe; desktop callback enqueues an event.
            self._route_text(text)
            with self._lock:
                running = self._running
            if running:
                self._set_state("THINKING")
        except Exception as exc:
            self._log.exception("event=router_error")
            self._recover(f"Не удалось передать команду маршрутизатору: {exc}")

    def speak(self, text: str) -> None:
        value = " ".join(str(text or "").split())
        if not value:
            self._log.warning("event=empty_tts")
            self.ui.post("voice_status", "Пустой ответ: озвучивать нечего.")
            return
        self._set_state("THINKING")
        self.tts_engine.speak(value)

    def _recover(self, message: str) -> None:
        self._set_state("ERROR", message)
        self.ui.post("voice_status", message)
        with self._lock:
            running = self._running
        if running:
            # Keep the input stream alive where possible; the capture supervisor handles device faults.
            time.sleep(RECOVERY_DELAYS[0])
            with self._lock:
                still_running = self._running
            if still_running and self.status()["state"] == "ERROR":
                self._set_state("LISTENING", "Голосовой контур восстановлен.")

    def _capture_worker(self, stop_event: threading.Event) -> None:
        delay_index = 0
        while not stop_event.is_set():
            try:
                capture = AudioCapture(
                    self._mic_lock, stop_event, self._capture_blocked,
                    self._enqueue_phrase,
                    lambda level: self.ui.post("audio_level", level),
                    self._on_mic_status,
                )
                capture.run()
                if stop_event.is_set():
                    break
                raise RuntimeError("Поток микрофона завершился неожиданно.")
            except Exception as exc:
                self._log.exception("event=capture_error")
                self._on_mic_status(False)
                self._set_state("ERROR", f"Микрофон недоступен: {exc}")
                delay = RECOVERY_DELAYS[min(delay_index, len(RECOVERY_DELAYS) - 1)]
                delay_index = min(delay_index + 1, len(RECOVERY_DELAYS) - 1)
                if stop_event.wait(delay):
                    break
                with self._lock:
                    if not self._running or self._shutdown:
                        break
                self._set_state("LISTENING", "Повторное подключение к микрофону.")
        with self._lock:
            if self._capture_thread is threading.current_thread():
                self._capture_thread = None
                self._capture_stop = None
                restart = self._running and self._restart_after_capture and not self._shutdown
                if restart:
                    self._launch_capture_locked()
                elif not self._running:
                    self._set_state("IDLE")
        self._log.info("event=capture_worker_exit")

    def _on_mic_status(self, ok: bool) -> None:
        with self._lock:
            self._mic_ok = bool(ok)
            running = self._running
        self.ui.post("mic_status", bool(ok))
        if ok and running:
            self._set_state("LISTENING")

    def _enqueue_phrase(self, audio: bytes) -> None:
        if not audio:
            self._log.warning("event=empty_audio")
            self.ui.post("voice_status", "Микрофон вернул пустой аудиофрагмент.")
            return
        # Publish UNDERSTANDING before waking the STT worker; otherwise a fast
        # transcript could set THINKING and then be overwritten by this producer.
        self._set_state("UNDERSTANDING")
        try:
            self._stt_queue.put_nowait(audio)
        except queue.Full:
            self._log.warning("event=stt_queue_full")
            self.ui.post("voice_status", "Очередь распознавания занята; фраза пропущена.")
            with self._lock:
                running = self._running
            if running:
                self._set_state("LISTENING")

    def _stt_worker(self) -> None:
        while True:
            try:
                audio = self._stt_queue.get(timeout=0.25)
            except queue.Empty:
                with self._lock:
                    if self._shutdown:
                        return
                continue
            if audio is None:
                return
            with self._lock:
                running = self._running
            if not running or self._is_speaking.is_set():
                continue
            last_error = None
            if stt.quota_exceeded():
                self._quota_exceeded = True
                last_error = RuntimeError(stt.QUOTA_MESSAGE)
            engine = stt.current_engine()
            attempts = ((0, 0.0),) if engine == "groq" else (() if stt.quota_exceeded() else tuple(enumerate(RECOVERY_DELAYS[:3])))
            for attempt, delay in attempts:
                with self._lock:
                    if self._shutdown or not self._running:
                        break
                if delay and self._stt_queue.empty():
                    time.sleep(delay if attempt else 0)
                try:
                    self.stt_engine.transcribe_bytes(audio)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    self._log.exception("event=stt_attempt_failed attempt=%s", attempt + 1)
                    # Quota/rate-limit HTTP 429 cannot be fixed by repeating the same request.
                    error_text = str(exc).lower()
                    if stt.quota_exceeded() or ("http 429" in error_text and any(
                        marker in error_text for marker in ("quota", "rate limit", "limit exceeded", "resource_exhausted", "free tier")
                    )):
                        self._quota_exceeded = True
                        last_error = RuntimeError(stt.QUOTA_MESSAGE)
                        break
            if last_error is not None:
                if self._quota_exceeded or stt.quota_exceeded():
                    if stt.current_engine() == "groq":
                        message = f"Квота Gemini STT исчерпана; резервный Groq тоже не сработал: {last_error}"
                    else:
                        message = stt.QUOTA_MESSAGE
                    self._set_state("DEGRADED", message)
                    self.ui.post("voice_status", message)
                else:
                    self._recover(f"Ошибка распознавания: {last_error}")
            with self._lock:
                running = self._running
                state = self._state
            if running and state in {"UNDERSTANDING", "ERROR"} and not self._is_speaking.is_set():
                # Don't overwrite THINKING while router/LLM is working.
                if state == "UNDERSTANDING":
                    self._set_state("LISTENING")

    def _tts_started(self) -> None:
        self._tts_off = False
        self._is_speaking.set()
        self._set_state("SPEAKING")

    def _tts_ended(self, succeeded: bool = True) -> None:
        self._is_speaking.clear()
        with self._lock:
            running = self._running
        if not succeeded:
            if running:
                threading.Thread(target=self._restore_after_error, daemon=True, name="jarvis-tts-recovery").start()
            else:
                self._set_state("IDLE")
            return
        if self.tts_engine.has_pending():
            self._set_state("THINKING")
        else:
            self._set_state("LISTENING" if running else "IDLE")

    def _restore_after_error(self) -> None:
        time.sleep(RECOVERY_DELAYS[0])
        with self._lock:
            running = self._running
            state = self._state
        if running and state == "ERROR":
            self._set_state("LISTENING", "Голосовой контур восстановлен после ошибки TTS.")

    def _tts_error(self, exc: Exception) -> None:
        self._log.error("event=tts_error error=%s", exc)
        error = str(exc)
        if "http 400" in error.lower() and ("voice" in error.lower() or "speaker" in error.lower()):
            message = "Gemini отклонил параметры озвучки (HTTP 400). Текстовый ответ доступен; голосовой контур продолжает работу."
        else:
            message = f"Озвучка недоступна, вот текстовый ответ: {error}"
        self._tts_off = True
        self._set_state("DEGRADED" if stt.quota_exceeded() else "ERROR", message)
        self.tts_engine.stop()
        self.ui.post("tts_error", str(exc))
        self.ui.post("voice_status", message)
        with self._lock:
            running = self._running
        if running:
            time.sleep(RECOVERY_DELAYS[0])
            with self._lock:
                running = self._running
            if running:
                self._set_state("LISTENING")
