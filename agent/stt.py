"""Cloud speech-to-text with Gemini primary and optional Groq fallback.

Groq transcription is used only when GROQ_API_KEY is configured; the assistant
never silently downloads or runs a local speech model.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_STT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
DEFAULT_GROQ_STT_MODEL = "whisper-large-v3-turbo"
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _model() -> str:
    return (os.environ.get("JARVIS_STT_MODEL") or DEFAULT_STT_MODEL).strip()


def _token() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("JARVIS_CHAT_KEY") or "").strip()


def _groq_token() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


def available_engines() -> list[str]:
    engines = []
    if _token():
        engines.append("gemini")
    if _groq_token():
        engines.append("groq")
    return engines


def current_engine() -> str:
    mode = os.environ.get("JARVIS_STT", "auto").strip().lower()
    if mode == "off":
        return "off"
    if mode == "groq":
        return "groq" if _groq_token() else "off"
    if mode == "gemini":
        return "gemini" if _token() else ("groq" if _groq_token() else "off")
    if _token():
        return "gemini"
    return "groq" if _groq_token() else "off"


def _request_timeout() -> float:
    try:
        return max(5.0, min(180.0, float(os.environ.get("JARVIS_STT_TIMEOUT", "30") or "30")))
    except (TypeError, ValueError):
        return 30.0


def _timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, (TimeoutError, socket.timeout)) or "timed out" in str(exc.reason).lower()
    return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()


def _gemini_health_check(timeout: float = 10.0) -> str:
    token = _token()
    if not token:
        raise RuntimeError("Не задан GEMINI_API_KEY для облачного распознавания речи.")
    url = DEFAULT_STT_URL + urllib.parse.quote(_model(), safe="-._") + "?" + urllib.parse.urlencode({"key": token})
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, min(20.0, float(timeout)))) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict) or not body.get("name"):
            raise RuntimeError("Gemini STT вернул неожиданный ответ проверки модели.")
        return "ONLINE"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Gemini STT: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        if _timeout_error(exc):
            raise RuntimeError(f"Gemini STT: тайм-аут проверки модели ({exc.reason}).") from exc
        raise RuntimeError(f"Gemini STT: сеть недоступна ({exc.reason}).") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Gemini STT: тайм-аут проверки модели ({exc}).") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Gemini STT вернул некорректный JSON при проверке доступности.") from exc


def _groq_health_check(timeout: float = 10.0) -> str:
    token = _groq_token()
    if not token:
        raise RuntimeError("Резервное распознавание Groq не настроено: нет GROQ_API_KEY.")
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, min(20.0, float(timeout)))) as response:
            body = json.loads(response.read().decode("utf-8"))
        models = {str(item.get("id", "")) for item in body.get("data", []) if isinstance(item, dict)}
        wanted = (os.environ.get("JARVIS_STT_FALLBACK_MODEL") or DEFAULT_GROQ_STT_MODEL).strip()
        if models and wanted not in models:
            raise RuntimeError(f"Groq не сообщает доступную модель распознавания {wanted}.")
        return "ONLINE"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Groq STT: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        if _timeout_error(exc):
            raise RuntimeError(f"Groq STT: тайм-аут проверки ({exc.reason}).") from exc
        raise RuntimeError(f"Groq STT: сеть недоступна ({exc.reason}).") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Groq STT: тайм-аут проверки ({exc}).") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Groq STT вернул некорректный JSON при проверке доступности.") from exc


def health_check(timeout: float = 10.0) -> str:
    """Check the primary STT model, using configured Groq only as a real fallback."""
    primary_error = None
    if _token():
        try:
            return _gemini_health_check(timeout)
        except Exception as exc:
            primary_error = exc
    if _groq_token():
        try:
            result = _groq_health_check(timeout)
            return "ONLINE (Groq reserve)" if primary_error else result
        except Exception as fallback_error:
            if primary_error:
                raise RuntimeError(f"Gemini STT недоступен: {primary_error}. Резерв Groq недоступен: {fallback_error}") from fallback_error
            raise
    if primary_error:
        raise primary_error
    raise RuntimeError("Не настроено облачное распознавание: укажите GEMINI_API_KEY или GROQ_API_KEY.")


def warmup() -> None:
    health_check()


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".mpeg": "audio/mpeg",
        ".mp4": "audio/mp4", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".flac": "audio/flac", ".webm": "audio/webm",
    }.get(suffix, "application/octet-stream")


def _transcribe_groq(path: Path) -> str:
    token = _groq_token()
    if not token:
        raise RuntimeError("Резервное распознавание не настроено: добавьте GROQ_API_KEY.")
    boundary = "----JarvisBoundary" + os.urandom(12).hex()
    filename = path.name.replace('"', "")
    mime = _mime_type(path)
    parts = []
    fields = {
        "model": (os.environ.get("JARVIS_STT_FALLBACK_MODEL") or DEFAULT_GROQ_STT_MODEL).strip(),
        "language": "ru",
        "response_format": "json",
        "temperature": "0",
    }
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8")
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n".encode("utf-8") + path.read_bytes() + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        GROQ_STT_URL,
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_request_timeout()) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Резервный Groq STT: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        if _timeout_error(exc):
            raise RuntimeError(f"Тайм-аут резервного распознавания Groq ({_request_timeout():g} с).") from exc
        raise RuntimeError(f"Не удалось подключиться к резервному Groq STT: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Тайм-аут резервного распознавания Groq ({_request_timeout():g} с).") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Groq STT вернул некорректный JSON.") from exc
    text = body.get("text", "") if isinstance(body, dict) else ""
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Groq STT не вернул распознанный текст.")
    return text.strip()


def _transcribe_gemini(path: Path, token: str) -> str:
    audio = path.read_bytes()
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": "Точно распознай речь в аудио. Язык русский. Верни только распознанные слова без комментариев."},
            {"inline_data": {"mime_type": _mime_type(path), "data": base64.b64encode(audio).decode("ascii")}}
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}
    }
    primary = _model()
    candidates = [primary]
    if primary == DEFAULT_STT_MODEL:
        candidates.extend(["gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"])
    last_error = None
    for model in dict.fromkeys(candidates):
        url = DEFAULT_STT_URL + urllib.parse.quote(model, safe="-._") + ":generateContent?" + urllib.parse.urlencode({"key": token})
        request = urllib.request.Request(
            url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST"
        )
        result = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=_request_timeout()) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = RuntimeError(f"Ошибка распознавания Gemini ({model}): HTTP {exc.code}. {detail}")
                # Daily quota exhaustion is not transient: do not call the same model again.
                if exc.code == 429 and any(
                    marker in detail.lower() for marker in ("quota", "resource_exhausted", "free_tier", "daily limit")
                ):
                    raise last_error from exc
                model_missing = exc.code in {400, 404} and any(
                    marker in detail.lower() for marker in ("model", "not found", "unknown", "does not exist")
                )
                if model_missing and model != candidates[-1]:
                    break
                if exc.code in {500, 502, 503, 504} and attempt == 0:
                    time.sleep(0.5)
                    continue
                if exc.code == 429 and attempt == 0:
                    time.sleep(0.5)
                    continue
                raise last_error from exc
            except (TimeoutError, socket.timeout) as exc:
                last_error = RuntimeError(f"Тайм-аут распознавания Gemini ({_request_timeout():g} с).")
                raise last_error from exc
            except urllib.error.URLError as exc:
                if _timeout_error(exc):
                    last_error = RuntimeError(f"Тайм-аут распознавания Gemini ({_request_timeout():g} с).")
                    raise last_error from exc
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                last_error = RuntimeError(f"Не удалось подключиться к Gemini STT: {exc.reason}")
                raise last_error from exc
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError("Gemini STT вернул некорректный JSON.") from exc
        if result is None:
            if last_error:
                message = str(last_error).lower()
                if any(x in message for x in ("http 404", "http 400", "not found", "unknown model", "does not exist")):
                    continue
                raise last_error
            continue
        try:
            text = "".join(part.get("text", "") for part in result["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            text = ""
        if text.strip():
            return text.strip()
        raise RuntimeError("Gemini не вернул распознанный текст. Проверьте качество аудио и лимит API.")
    if last_error:
        raise last_error
    raise RuntimeError("Не удалось выбрать доступную модель Gemini для распознавания.")


def transcribe(audio_path: str) -> str:
    engine = current_engine()
    if engine == "off":
        raise RuntimeError("Голосовой ввод требует GEMINI_API_KEY или резервный GROQ_API_KEY. Добавьте ключ в Центре управления.")
    path = Path(audio_path)
    if not path.is_file():
        raise ValueError(f"Файл не найден: {audio_path}")
    audio_size = path.stat().st_size
    if audio_size <= 0:
        raise ValueError("Аудиофайл пустой.")
    if audio_size > 18 * 1024 * 1024:
        raise ValueError("Аудиофайл слишком большой для одного запроса JARVIS (лимит 18 МБ).")
    if engine == "groq":
        return _transcribe_groq(path)
    token = _token()
    try:
        return _transcribe_gemini(path, token)
    except Exception as primary_error:
        if not _groq_token():
            raise
        try:
            return _transcribe_groq(path)
        except Exception as fallback_error:
            raise RuntimeError(
                f"Gemini STT не сработал: {primary_error}. Резервный Groq STT тоже не сработал: {fallback_error}"
            ) from fallback_error
