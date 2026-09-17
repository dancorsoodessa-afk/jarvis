"""Unified desktop voice engine: two claps -> speech -> core -> TTS."""
import os, time, wave
from pathlib import Path
from .logging_setup import get as get_log
from . import stt, tts, voice
from .state import JarvisState

class Recorder:
    def __init__(self, samplerate: int = 16000): self.samplerate = samplerate
    def record(self, out_path: Path) -> Path:
        try:
            import numpy as np, sounddevice as sd
        except ImportError as exc: raise RuntimeError("Микрофон недоступен: установите voice-зависимости") from exc
        chunk=int(0.1*self.samplerate); frames=[]; silence=0.0; spoken=0.0; started=time.time()
        with sd.InputStream(samplerate=self.samplerate, channels=1, dtype="int16"):
            while time.time()-started < 10:
                data,_=sd.rec(chunk,samplerate=self.samplerate,channels=1,dtype="int16"); sd.wait(); frames.append(data.copy())
                level=float(np.abs(data).mean())/32768.0
                if level>0.01: silence=0.0; spoken+=0.1
                elif spoken>0: silence+=0.1
                if spoken>=0.2 and silence>=0.7: break
        if spoken<0.2: raise RuntimeError("Речь не обнаружена")
        out_path.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(out_path),"wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(self.samplerate); wav.writeframes(b"".join(f.tobytes() for f in frames))
        return out_path

class VoiceLoop:
    def __init__(self, agent, recorder: Recorder | None = None, **_legacy):
        self.agent=agent; self.recorder=recorder; self.log=get_log("voice"); self.tmp_dir=os.environ.get("JARVIS_HOME", ".")
    def listen_once(self, recorder=None) -> str:
        rec=recorder or self.recorder
        if rec is not None:
            wav=Path(self.tmp_dir)/"jarvis_mic.wav"; rec.record(wav)
            try: return stt.transcribe(str(wav)).strip()
            finally:
                try: wav.unlink()
                except OSError: pass
        self.agent.state.listening(); return voice.listen_for_phrase()
    def step(self, heard: str) -> str | None: return self.agent.handle(heard).text
    def run(self):
        if not voice.available(): raise RuntimeError("Голосовой ввод недоступен: установите sounddevice и numpy")
        self.log.info("Голосовой режим: ожидание двух хлопков")
        while True:
            try:
                self.agent.state.set(JarvisState.LISTENING)
                heard=voice.listen_for_double_clap_and_command(on_speech_start=tts.stop)
                if not heard: self.agent.state.idle(); continue
                result=self.agent.handle(heard); answer=str(result.text or "").strip()
                if answer: self.agent.state.speaking(); tts.speak_and_play(answer)
                self.agent.state.idle()
            except KeyboardInterrupt: self.agent.state.exiting(); raise
            except Exception as exc:
                self.agent.state.error(); self.log.warning("Ошибка голосового цикла: %s", exc, exc_info=True); time.sleep(1)
