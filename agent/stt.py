"""Speech-to-text: local Whisper is the default; Gemini/Groq are explicit or legacy-auto options."""
from __future__ import annotations
import base64, json, os, urllib.error, urllib.parse, urllib.request
from functools import lru_cache
from pathlib import Path

DEFAULT_LOCAL_MODEL = "small"
DEFAULT_STT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

def _model() -> str:
    return (os.environ.get("JARVIS_STT_MODEL") or DEFAULT_STT_MODEL).strip()

def _token() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()

def _local_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False

def available_engines() -> list[str]:
    engines = ["local"] if _local_available() else []
    if _token(): engines.append("gemini")
    if os.environ.get("GROQ_API_KEY", "").strip(): engines.append("groq")
    return engines

def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "local").strip().lower()
    if mode == "off": return "off"
    if mode in ("local", "whisper"):
        return "local" if _local_available() else "off"
    if mode == "gemini": return "gemini" if _token() else "off"
    if mode == "groq": return "groq" if os.environ.get("GROQ_API_KEY", "").strip() else "off"
    if mode == "auto":
        # Legacy auto mode: cloud providers only when configured. Default mode remains local.
        if _token(): return "gemini"
        if os.environ.get("GROQ_API_KEY", "").strip(): return "groq"
        return "off"
    return "off"

def _request_timeout() -> float:
    try: return max(5.0, min(180.0, float(os.environ.get("JARVIS_STT_TIMEOUT", "45") or "45")))
    except (TypeError, ValueError): return 45.0

@lru_cache(maxsize=2)
def _local_model(name: str):
    from faster_whisper import WhisperModel
    cache = os.environ.get("JARVIS_WHISPER_CACHE", "").strip() or None
    return WhisperModel(name, device="cpu", compute_type="int8", download_root=cache)

def health_check(timeout: float = 10.0) -> str:
    engine = current_engine()
    if engine == "local": return "LOCAL_READY"
    if engine == "off": raise RuntimeError("Распознавание отключено или недоступно. Установите локальный компонент Whisper либо выберите облачный режим.")
    return "CLOUD_SELECTED"

def warmup() -> None:
    health_check()

def _transcribe_gemini(path: Path) -> str:
    token = _token()
    if not token: raise RuntimeError("Не задан GEMINI_API_KEY для распознавания речи.")
    audio = path.read_bytes()
    if not audio: raise ValueError("Аудиофайл пустой.")
    if len(audio) > 18 * 1024 * 1024: raise ValueError("Аудиофайл слишком большой для одного запроса Gemini (лимит JARVIS — 18 МБ).")
    suffix = path.suffix.lower()
    mime = "audio/wav" if suffix == ".wav" else "audio/mpeg" if suffix == ".mp3" else "audio/" + suffix.lstrip(".")
    payload = {"contents":[{"role":"user","parts":[
        {"text":"Точно распознай речь в аудио. Язык русский. Верни только распознанные слова без комментариев."},
        {"inline_data":{"mime_type":mime,"data":base64.b64encode(audio).decode("ascii")}}]}],
        "generationConfig":{"temperature":0,"maxOutputTokens":1024}}
    url = DEFAULT_STT_URL + _model() + ":generateContent?" + urllib.parse.urlencode({"key":token})
    req = urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=_request_timeout()) as response: result=json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")[:500]
        raise RuntimeError(f"Ошибка распознавания Gemini: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc: raise RuntimeError(f"Не удалось подключиться к Gemini STT: {exc.reason}") from exc
    except (json.JSONDecodeError,UnicodeDecodeError) as exc: raise RuntimeError("Gemini STT вернул некорректный JSON.") from exc
    try: text="".join(p.get("text","") for p in result["candidates"][0]["content"]["parts"]).strip()
    except (KeyError,IndexError,TypeError): text=""
    if not text: raise RuntimeError("Gemini не вернул распознанный текст.")
    return text

def _transcribe_groq(path: Path) -> str:
    token=os.environ.get("GROQ_API_KEY","").strip()
    if not token: raise RuntimeError("Не задан GROQ_API_KEY для резервного распознавания.")
    boundary="----JarvisBoundary7MA4YWxkTrZu0gW"
    mime="audio/wav" if path.suffix.lower()==".wav" else "audio/mpeg" if path.suffix.lower()==".mp3" else "application/octet-stream"
    filename=path.name or "audio.wav"
    chunks=[]
    def field(name,value):
        chunks.extend([f"--{boundary}\r\n".encode(),f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),value.encode(),b"\r\n"])
    chunks.extend([f"--{boundary}\r\n".encode(),f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),f"Content-Type: {mime}\r\n\r\n".encode(),path.read_bytes(),b"\r\n"])
    field("model","whisper-large-v3-turbo"); field("language","ru")
    chunks.append(f"--{boundary}--\r\n".encode())
    req=urllib.request.Request(GROQ_STT_URL,data=b"".join(chunks),headers={"Authorization":f"Bearer {token}","Content-Type":f"multipart/form-data; boundary={boundary}","Accept":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=_request_timeout()) as response: result=json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")[:500]
        raise RuntimeError(f"Ошибка распознавания Groq: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc: raise RuntimeError(f"Не удалось подключиться к Groq STT: {exc.reason}") from exc
    try: text=str(result.get("text","")).strip()
    except AttributeError: text=""
    if not text: raise RuntimeError("Groq не вернул распознанный текст.")
    return text

def transcribe(audio_path: str) -> str:
    engine=current_engine()
    if engine=="off": raise RuntimeError("Распознавание отключено или недоступно. Для бесплатного распознавания без API-квот установите локальный Whisper.")
    path=Path(audio_path)
    if not path.is_file(): raise ValueError(f"Файл не найден: {audio_path}")
    if engine=="local":
        name=(os.environ.get("JARVIS_WHISPER_MODEL") or DEFAULT_LOCAL_MODEL).strip()
        try:
            model=_local_model(name)
            segments,_=model.transcribe(str(path),language="ru",beam_size=5,vad_filter=True)
            text=" ".join(s.text.strip() for s in segments).strip()
        except Exception as exc:
            raise RuntimeError("Локальный Whisper не запустился. При первом запуске модель скачивается один раз; проверьте интернет и свободное место. Детали: "+str(exc)) from exc
        if not text: raise RuntimeError("Whisper не распознал речь. Проверьте микрофон и повторите.")
        return text
    if engine=="gemini":
        try: return _transcribe_gemini(path)
        except RuntimeError as exc:
            # Groq fallback is used only in legacy auto mode and only if explicitly configured.
            if os.environ.get("JARVIS_STT","local").strip().lower()=="auto" and os.environ.get("GROQ_API_KEY","").strip():
                return _transcribe_groq(path)
            raise
    if engine=="groq": return _transcribe_groq(path)
    raise RuntimeError("Неизвестный режим распознавания речи.")
