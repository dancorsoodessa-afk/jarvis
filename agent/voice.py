"""Стабильный захват микрофона JARVIS: sounddevice -> Vosk."""
from __future__ import annotations
import os, tempfile, wave
from pathlib import Path

SAMPLE_RATE=16000
BLOCK_SECONDS=0.05
MIN_SPEECH_SECONDS=0.25

def available()->bool:
    try:
        import numpy, sounddevice
        from . import stt
        return bool(stt.available_engines())
    except ImportError:
        return False

def _rms(block)->float:
    import numpy as np
    a=np.asarray(block,dtype="float32")
    return float((a*a).mean()**0.5)/32768.0 if a.size else 0.0

def _device():
    value=os.environ.get("JARVIS_INPUT_DEVICE","").strip()
    if not value: return None
    try: return int(value)
    except ValueError: return value

def _write_wav(frames)->Path:
    fd,name=tempfile.mkstemp(prefix="jarvis_mic_",suffix=".wav"); os.close(fd)
    path=Path(name)
    import numpy as np
    raw=np.concatenate(frames).astype("int16")
    with wave.open(str(path),"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE); w.writeframes(raw.tobytes())
    return path

def listen_for_phrase(samplerate:int=SAMPLE_RATE,silence_seconds:float=0.80,max_seconds:float=10.0,start_timeout:float=5.0,on_speech_start=None)->str:
    import numpy as np, sounddevice as sd
    block_size=max(400,int(samplerate*BLOCK_SECONDS))
    start_blocks=max(1,int(start_timeout/BLOCK_SECONDS))
    silence_blocks=max(1,int(silence_seconds/BLOCK_SECONDS))
    max_blocks=max(1,int(max_seconds/BLOCK_SECONDS))
    frames=[]; started=False; silent=0
    try:
        with sd.InputStream(samplerate=samplerate,blocksize=block_size,channels=1,dtype="int16",device=_device()) as stream:
            noise=[]
            for _ in range(10):
                data,_=stream.read(block_size); noise.append(_rms(data[:,0]))
            baseline=sorted(noise)[max(0,int(len(noise)*0.7)-1)] if noise else 0.003
            threshold=max(0.008,baseline*2.0); end_threshold=max(0.005,baseline*1.25)
            for i in range(start_blocks+max_blocks):
                data,_=stream.read(block_size); block=np.asarray(data[:,0],dtype=np.int16).copy(); level=_rms(block)
                if not started:
                    if level>=threshold:
                        started=True; frames.append(block)
                        if on_speech_start:
                            try: on_speech_start()
                            except Exception: pass
                    elif i>=start_blocks: return ""
                    continue
                frames.append(block); silent=silent+1 if level<end_threshold else 0
                if len(frames)>=int(MIN_SPEECH_SECONDS/BLOCK_SECONDS) and silent>=silence_blocks: break
                if len(frames)>=max_blocks: break
    except Exception as exc:
        raise RuntimeError(f"Не удалось открыть микрофон: {exc}") from exc
    if not started or len(frames)<int(MIN_SPEECH_SECONDS/BLOCK_SECONDS): return ""
    path=_write_wav(frames)
    try:
        from . import stt
        return stt.transcribe(str(path)).strip()
    finally:
        try: path.unlink()
        except OSError: pass

def list_input_devices():
    import sounddevice as sd
    return sd.query_devices()

def listen_for_double_clap_and_command(on_speech_start=None,samplerate:int=SAMPLE_RATE)->str:
    return listen_for_phrase(samplerate=samplerate,on_speech_start=on_speech_start)

def listen_for_wake_and_command(on_speech_start=None,samplerate:int=SAMPLE_RATE):
    return listen_for_phrase(samplerate=samplerate,on_speech_start=on_speech_start)

def record_and_transcribe(seconds=10,samplerate:int=SAMPLE_RATE):
    return listen_for_phrase(samplerate=samplerate,max_seconds=min(float(seconds),10.0))
