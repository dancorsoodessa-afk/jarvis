"""Voice activation for desktop JARVIS: double clap + 10-second VAD."""
from __future__ import annotations
import os, tempfile, time, wave
from pathlib import Path

def available() -> bool:
    try:
        import sounddevice, numpy
        return True
    except ImportError:
        return False

def _rms(block) -> float:
    import numpy as np
    a=np.asarray(block,dtype="float32")
    return float((a*a).mean()**0.5)

def _recognize(frames: bytes, samplerate: int) -> str:
    fd,name=tempfile.mkstemp(prefix="jarvis_mic_",suffix=".wav"); os.close(fd); path=Path(name)
    try:
        with wave.open(str(path),"wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(samplerate); w.writeframes(frames)
        try:
            from . import stt
            if stt.current_engine()!="off":
                text=stt.transcribe(str(path)).strip()
                if text: return text
        except Exception: pass
        import speech_recognition as sr
        r=sr.Recognizer()
        with sr.AudioFile(str(path)) as source: audio=r.record(source)
        try: return r.recognize_google(audio,language="ru-RU").strip()
        except sr.UnknownValueError: return ""
        except sr.RequestError as exc: raise RuntimeError(f"Сервис распознавания речи недоступен: {exc}") from exc
    finally:
        try: path.unlink()
        except OSError: pass

def listen_for_phrase(samplerate=16000,silence_seconds=.55,max_seconds=10.0,start_timeout=5.0,on_speech_start=None):
    import sounddevice as sd, numpy as np
    bs=int(samplerate*.03); silent_limit=max(1,int(silence_seconds/.03)); max_blocks=max(1,int(max_seconds/.03)); timeout_blocks=max(1,int(start_timeout/.03)); chunks=[]; started=False; silent=0; ambient=[]
    try:
        with sd.InputStream(samplerate=samplerate,channels=1,dtype="int16",blocksize=bs) as stream:
            for i in range(timeout_blocks+max_blocks):
                data,overflow=stream.read(bs)
                if overflow: continue
                block=np.asarray(data[:,0],dtype=np.int16).copy(); level=_rms(block)
                if not started:
                    if i<10: ambient.append(level)
                    noise=sum(ambient)/len(ambient) if ambient else 250.0
                    if level>=max(500.0,noise*2.8):
                        started=True; chunks.append(block)
                        if on_speech_start:
                            try: on_speech_start()
                            except Exception: pass
                    if i>=timeout_blocks: return ""
                    continue
                chunks.append(block); noise=sum(ambient)/len(ambient) if ambient else 250.0; silent=silent+1 if level<max(500.0,noise*2.2) else 0
                if len(chunks)>=12 and silent>=silent_limit: break
                if len(chunks)>=max_blocks: break
    except Exception as exc: raise RuntimeError(f"Не удалось открыть микрофон: {exc}") from exc
    if not started or not chunks: return ""
    raw=np.concatenate(chunks).astype(np.int16); trim=min(len(raw),int(samplerate*silence_seconds)); raw=raw[:-trim] if trim and len(raw)>trim else raw
    return _recognize(raw.tobytes(),samplerate)

def listen_for_double_clap_and_command(on_speech_start=None,samplerate=16000):
    import sounddevice as sd
    last=0.0; bs=int(samplerate*.08)
    while True:
        data=sd.rec(bs,samplerate=samplerate,channels=1,dtype="int16",blocking=True); level=_rms(data[:,0]); now=time.monotonic()
        if level>=6500.0:
            if now-last<=.8:
                last=0.0
                return listen_for_phrase(samplerate=samplerate,silence_seconds=.55,max_seconds=10.0,start_timeout=5.0,on_speech_start=on_speech_start)
            last=now
        elif last and now-last>.8: last=0.0

def listen_for_wake_and_command(on_speech_start=None,samplerate=16000):
    return listen_for_double_clap_and_command(on_speech_start,samplerate)

def record_and_transcribe(seconds=10,samplerate=16000):
    return listen_for_phrase(samplerate=samplerate,max_seconds=min(float(seconds),10.0),start_timeout=5.0)
