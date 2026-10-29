"""Провайдер чата для OpenAI-совместимых API."""

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import time
import threading
from pathlib import Path
from typing import Optional

DEFAULT_SYSTEM_PROMPT = (
    "Ты — Джарвис, персональный ИИ-ассистент пользователя. "
    "Всегда отвечай на русском языке, если пользователь явно не попросил другой язык. "
    "Понимай обычную человеческую речь без специальных команд, слешей и названий инструментов. "
    "Сам определяй намерение пользователя и сам выбирай нужный инструмент. Пользователь не обязан знать, как называется инструмент. "
    "Не предлагай пользователю команды вроде calc, status, search и не перечисляй доступные инструменты, если он об этом прямо не спросил. "
    "Для вычислений, проверки системы, поиска файлов, запуска приложений, изменения громкости и работы с файлами сразу выполняй действие подходящим инструментом. "
    "Не заставляй пользователя выполнять действие вручную, если ты можешь выполнить его инструментом. "
    "Перед опасным действием дождись явного подтверждения пользователя. "
    "Отвечай понятно, кратко и по делу. Не выдумывай результат: если действие не выполнено или недоступно, прямо сообщи об этом."
)

MAX_HISTORY_MESSAGES = 12
_MODEL_CACHE: dict[tuple[str, str], tuple[float, set[str]]] = {}
_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE_TTL = 300
CONFIRMATION_PREFIX = "Инструмент «"


class OpenAIChatProvider:
    name = "Джарвис ИИ"

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, timeout: int = 30,
                 history: Optional[list] = None,
                 system_prompt: Optional[str] = None, fallback_models: Optional[list[str]] = None):
        self.url = (url or os.environ.get("JARVIS_CHAT_URL", "")).strip()
        # An explicitly supplied empty key is intentional (the user cleared it).
        # Only consult environment variables when no key argument was supplied.
        if api_key is None:
            configured_key = os.environ.get("JARVIS_CHAT_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        else:
            configured_key = api_key
        self.api_key = str(configured_key or "").strip()
        self.model = (model or os.environ.get("JARVIS_CHAT_MODEL", "")).strip()
        self.timeout = timeout
        self.history: list[dict] = history if history is not None else []
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.tool_executor = None
        self.on_delta = None
        self._discovered_model: str | None = None
        self._model_verified = False
        self.fallback_models = [str(x).strip() for x in (fallback_models or []) if str(x).strip()]
        self.last_used_model = self.model

    def _ensure_endpoint(self) -> None:
        from urllib.parse import urlsplit
        from agent.config import DEFAULT_CHAT_URL

        if not self.url:
            self.url = DEFAULT_CHAT_URL
        parsed = urlsplit(self.url)
        allowed_hosts = {"generativelanguage.googleapis.com", "api.groq.com"}
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or not parsed.path.endswith("/chat/completions"):
            raise RuntimeError("Разрешены только защищённые официальные endpoint Gemini и Groq.")

    def _provider_name(self) -> str:
        return "Groq" if urllib.parse.urlsplit(self.url).hostname == "api.groq.com" else "Gemini"

    def _messages(self, prompt) -> list[dict]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history[-MAX_HISTORY_MESSAGES:])
        if isinstance(prompt, dict) and isinstance(prompt.get("attachment"), dict):
            text = str(prompt.get("text") or "")
            attachment = prompt["attachment"]
            name = str(attachment.get("name") or "file")
            mime = str(attachment.get("mime") or "application/octet-stream").lower()
            data = str(attachment.get("data") or "")
            parts = [{"type": "text", "text": text}]
            if data:
                if mime.startswith("image/"):
                    parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
                elif mime.startswith("audio/"):
                    fmt = mime.split("/")[-1].split(";")[0]
                    if fmt == "mpeg":
                        fmt = "mp3"
                    parts.append({"type": "input_audio", "input_audio": {"data": data, "format": fmt}})
                elif mime.startswith("text/") or any(x in mime for x in ("json", "csv", "xml", "markdown")):
                    import base64
                    try:
                        decoded = base64.b64decode(data).decode("utf-8", errors="replace")
                        parts.append({"type": "text", "text": f"Файл {name}:\\n{decoded}"})
                    except Exception:
                        parts.append({"type": "text", "text": f"Прикреплён файл: {name} ({mime})."})
                elif mime == "application/pdf" or any(x in mime for x in ("word", "excel", "spreadsheet", "presentation", "powerpoint")):
                    parts.append({"type": "file", "file": {"filename": name, "file_data": f"data:{mime};base64,{data}"}})
                else:
                    parts.append({"type": "text", "text": f"Прикреплён файл: {name} ({mime})."})
            messages.append({"role": "user", "content": parts})
        else:
            messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _normalize_model(model: str) -> str:
        # Groq model IDs are passed through unchanged.
        return model.strip()

    def _auth_headers(self, *, stream: bool = False) -> dict:
        if not self.api_key:
            host = urllib.parse.urlsplit(self.url).hostname or ""
            if host == "api.groq.com":
                raise RuntimeError("Не задан GROQ_API_KEY. Добавьте отдельный ключ Groq в Центре управления JARVIS.")
            raise RuntimeError("Не задан GEMINI_API_KEY. Создайте ключ в Google AI Studio и добавьте его в Центре управления JARVIS.")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        if stream:
            headers["Accept"] = "text/event-stream"
        return headers

    def _request(self, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._auth_headers()
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(3):
            req = urllib.request.Request(self.url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                quota_limited = exc.code == 429 and any(
                    marker in detail.lower()
                    for marker in ("quota", "resource_exhausted", "free_tier", "daily limit")
                )
                if exc.code in retryable and attempt < 2 and not quota_limited:
                    time.sleep(min(1.0 * (2 ** attempt), 2.0))
                    continue
                if exc.code == 503:
                    raise RuntimeError(f"{self._provider_name()} временно перегружен (HTTP 503). Повторите запрос через минуту. " + detail) from exc
                raise RuntimeError(f"Ошибка API: HTTP {exc.code}. {detail}") from exc
            except (TimeoutError, socket.timeout) as exc:
                raise RuntimeError(
                    f"Тайм-аут запроса к {self._provider_name()} ({self.timeout} с). "
                    "Проверьте соединение и повторите запрос."
                ) from exc
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)) or "timed out" in str(exc.reason).lower():
                    raise RuntimeError(
                        f"Тайм-аут запроса к {self._provider_name()} ({self.timeout} с). "
                        "Проверьте соединение и повторите запрос."
                    ) from exc
                if attempt < 2:
                    time.sleep(min(1.0 * (2 ** attempt), 2.0))
                    continue
                raise RuntimeError(f"Не удалось подключиться к ИИ: {exc.reason}") from exc
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError("ИИ вернул некорректный JSON-ответ") from exc
        raise RuntimeError(f"{self._provider_name()} временно недоступен после нескольких попыток.")

    def _models_url(self) -> str:
        parsed = urllib.parse.urlsplit(self.url)
        path = parsed.path
        if path.endswith("/chat/completions"):
            path = path[: -len("/chat/completions")] + "/models"
        elif path.endswith("/v1"):
            path += "/models"
        elif not path.endswith("/models"):
            path = path.rstrip("/") + "/models"
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    @staticmethod
    def _model_id(value: str) -> str:
        value = str(value or "").strip()
        return value.removeprefix("models/")

    def _available_models(self, *, refresh: bool = False) -> set[str]:
        self._ensure_endpoint()
        cache_key = (self.url.rstrip("/"), self.api_key)
        now = time.monotonic()
        with _MODEL_CACHE_LOCK:
            cached = _MODEL_CACHE.get(cache_key)
            if not refresh and cached and now - cached[0] < _MODEL_CACHE_TTL:
                return set(cached[1])
        if not self.api_key:
            raise RuntimeError("Не задан GEMINI_API_KEY. Добавьте ключ в Центре управления JARVIS.")
        req = urllib.request.Request(
            self._models_url(),
            headers={"Accept": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 12)) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code in (401, 403):
                raise RuntimeError(f"Ключ Gemini отклонён (HTTP {exc.code}). Проверьте API-ключ и доступ.") from exc
            raise RuntimeError(f"Не удалось получить список моделей Gemini: HTTP {exc.code}. {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Не удалось получить список моделей Gemini: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Gemini вернул некорректный JSON списка моделей.") from exc
        raw = body.get("data") if isinstance(body, dict) else None
        if not isinstance(raw, list):
            raise RuntimeError("Gemini не вернул список доступных моделей.")
        ids = {
            self._model_id(item.get("id", ""))
            for item in raw if isinstance(item, dict) and item.get("id")
        }
        ids = {item for item in ids if item}
        with _MODEL_CACHE_LOCK:
            _MODEL_CACHE[cache_key] = (time.monotonic(), set(ids))
        if not ids:
            raise RuntimeError("Список моделей Gemini пуст. Проверьте ключ, проект и доступ к Gemini API.")
        return ids

    @staticmethod
    def _select_flash_model(available: set[str]) -> str:
        preferred = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest")
        for model in preferred:
            if model in available:
                return model
        candidates = sorted(
            model for model in available
            if "flash" in model.lower()
            and not any(tag in model.lower() for tag in ("embedding", "tts", "transcribe", "image", "live", "robotics"))
        )
        return candidates[0] if candidates else ""

    @staticmethod
    def _persist_selected_model(model: str) -> None:
        if not model:
            return
        os.environ["GEMINI_MODEL"] = model
        os.environ["JARVIS_CHAT_MODEL"] = model
        # Persist only the selected model, never the API key. In packaged builds
        # the env-file path can be overridden to a writable per-user config file.
        configured = os.environ.get("JARVIS_ENV_FILE", "").strip()
        env_path = Path(configured) if configured else Path(__file__).resolve().parents[2] / "config" / ".env"
        try:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
            out = []
            replaced = False
            for line in lines:
                if line.strip().startswith("GEMINI_MODEL="):
                    if not replaced:
                        out.append(f"GEMINI_MODEL={model}")
                        replaced = True
                else:
                    out.append(line)
            if not replaced:
                out.append(f"GEMINI_MODEL={model}")
            env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
        except OSError:
            # A read-only installation must still continue with the in-memory model.
            pass

    def health_check(self) -> str:
        """Validate the API key, discover real model IDs and select an available Flash model."""
        available = self._available_models(refresh=True)
        current = self._model_id(self.model or os.environ.get("GEMINI_MODEL", ""))
        if current not in available:
            selected = self._select_flash_model(available)
            if not selected:
                raise RuntimeError(
                    f"Модель {current or '(не задана)'} недоступна; список ключа не содержит подходящей Gemini Flash-модели."
                )
            self.model = selected
            self._discovered_model = selected
            self.last_used_model = selected
            self._persist_selected_model(selected)
        else:
            self.model = current
            self._discovered_model = current
            self._persist_selected_model(current)
        self.fallback_models = [
            candidate for candidate in (
                "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest",
                *sorted(available),
            )
            if candidate in available and candidate != self.model
            and "flash" in candidate.lower()
            and not any(tag in candidate.lower() for tag in ("embedding", "tts", "transcribe", "image", "live", "robotics"))
        ]
        self.fallback_models = list(dict.fromkeys(self.fallback_models))
        self._model_verified = True
        return "ONLINE"

    def discover_model(self) -> str:
        # Validate once per provider instance before sending a generation request.
        # The shared model-list cache avoids repeated network calls across role profiles.
        if not self._model_verified:
            self.health_check()
        if not self.model:
            raise RuntimeError("Не удалось выбрать доступную модель Gemini Flash.")
        return self._normalize_model(self.model)

    def _request_stream(self, payload: dict) -> dict:
        data = json.dumps({**payload, "stream": True}, ensure_ascii=False).encode("utf-8")
        headers = self._auth_headers(stream=True)
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(3):
            req = urllib.request.Request(self.url, data=data, headers=headers)
            content_parts: list[str] = []
            tool_calls: list[dict] = []
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            piece = json.loads(chunk)["choices"][0].get("delta", {})
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        delta = piece.get("content") or ""
                        if delta:
                            content_parts.append(delta)
                            if self.on_delta:
                                try:
                                    self.on_delta(delta)
                                except Exception:
                                    pass
                        for tc in piece.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            dst = tool_calls[idx]
                            if tc.get("id"):
                                dst["id"] = tc["id"]
                            # Gemini 3 requires the thought signature to be echoed
                            # unchanged with the assistant tool-call message. The
                            # OpenAI-compatible endpoint carries it in extra_content.
                            extra = tc.get("extra_content")
                            if isinstance(extra, dict):
                                dst["extra_content"] = extra
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                dst["function"]["name"] += fn["name"]
                            if fn.get("arguments"):
                                dst["function"]["arguments"] += fn["arguments"]
                msg: dict = {"role": "assistant", "content": "".join(content_parts)}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                return {"choices": [{"message": msg}]}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                quota_limited = exc.code == 429 and any(
                    marker in detail.lower()
                    for marker in ("quota", "resource_exhausted", "free_tier", "daily limit")
                )
                if exc.code in retryable and attempt < 2 and not quota_limited:
                    time.sleep(min(1.0 * (2 ** attempt), 2.0))
                    continue
                if exc.code == 503:
                    raise RuntimeError(f"{self._provider_name()} временно перегружен (HTTP 503). Повторите запрос через минуту. " + detail) from exc
                raise RuntimeError(f"Ошибка API: HTTP {exc.code}. {detail}") from exc
            except (TimeoutError, socket.timeout) as exc:
                raise RuntimeError(
                    f"Тайм-аут запроса к {self._provider_name()} ({self.timeout} с). "
                    "Проверьте соединение и повторите запрос."
                ) from exc
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)) or "timed out" in str(exc.reason).lower():
                    raise RuntimeError(
                        f"Тайм-аут запроса к {self._provider_name()} ({self.timeout} с). "
                        "Проверьте соединение и повторите запрос."
                    ) from exc
                if attempt < 2:
                    time.sleep(min(1.0 * (2 ** attempt), 2.0))
                    continue
                raise RuntimeError(f"Не удалось подключиться к ИИ: {exc.reason}") from exc
        raise RuntimeError(f"{self._provider_name()} временно недоступен после нескольких попыток.")

    def _extract(self, body: dict) -> dict:
        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"ИИ вернул неожиданный ответ: {body!r}") from exc
        # Keep provider-specific metadata on tool calls; stripping extra_content
        # loses Gemini's required thought_signature and causes HTTP 400 next turn.
        tool_calls = []
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            normalized = {
                key: value for key, value in call.items()
                if key in {"id", "type", "function", "extra_content"}
            }
            tool_calls.append(normalized)
        return {"content": msg.get("content") or "", "tool_calls": tool_calls}

    def generate(self, prompt, tools: Optional[list] = None, max_steps: int = 4) -> str:
        self._ensure_endpoint()
        primary_model = self.discover_model()
        model_candidates = list(dict.fromkeys(
            [primary_model] + [item for item in self.fallback_models if item and item != primary_model]
        ))
        model = primary_model
        attempted_models = {primary_model}
        messages = self._messages(prompt)
        payload = {"model": model, "messages": messages, "temperature": 0.25}
        tools_enabled = os.environ.get("GEMINI_TOOLS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        active_tools = tools if tools_enabled else None
        # Safe mode is default: Gemini returns plain text; local tools remain
        # available through JarvisAgent's deterministic command router.
        if active_tools:
            payload["tools"] = active_tools

        result_content = ""
        for step_index in range(max_steps):
            try:
                body = self._request_stream(payload) if self.on_delta is not None and "tools" in payload else self._request(payload)
            except RuntimeError as exc:
                message = str(exc).lower()
                if "thought_signature" in message and "tools" in payload:
                    # One bounded recovery attempt: discard tool-call history and
                    # retry the same user turn as plain text. Never retry-loop.
                    safe_messages = [
                        item for item in messages
                        if item.get("role") != "tool"
                        and not (item.get("role") == "assistant" and item.get("tool_calls"))
                    ]
                    safe_payload = {key: value for key, value in payload.items() if key != "tools"}
                    safe_payload["messages"] = safe_messages
                    try:
                        body = self._request(safe_payload)
                        messages = safe_messages
                        payload = safe_payload
                    except RuntimeError as retry_exc:
                        raise RuntimeError(
                            "Gemini отклонил вызов инструмента из-за thought_signature; "
                            f"повтор без tools также не выполнен: {retry_exc}"
                        ) from retry_exc
                else:
                    body = None
                if body is None:
                    capacity_error = any(f"http {code}" in message for code in (429, 500, 502, 503, 504)) or "temporarily overloaded" in message
                    model_unavailable = (
                        any(f"http {code}" in message for code in (400, 404))
                        and any(marker in message for marker in (
                            "model", "not found", "unknown", "does not exist", "not available",
                        ))
                    )
                    if not (capacity_error or model_unavailable):
                        raise
                    last_error = exc
                    body = None
                    for fallback_model in model_candidates:
                        if fallback_model in attempted_models:
                            continue
                        attempted_models.add(fallback_model)
                        fallback_payload = {**payload, "model": fallback_model}
                        try:
                            body = self._request_stream(fallback_payload) if self.on_delta is not None and "tools" in fallback_payload else self._request(fallback_payload)
                            model = fallback_model
                            break
                        except RuntimeError as fallback_exc:
                            last_error = fallback_exc
                            fallback_message = str(fallback_exc).lower()
                            capacity_error = any(f"http {code}" in fallback_message for code in (429, 500, 502, 503, 504)) or "temporarily overloaded" in fallback_message
                            model_unavailable = (
                                any(f"http {code}" in fallback_message for code in (400, 404))
                                and any(marker in fallback_message for marker in (
                                    "model", "not found", "unknown", "does not exist", "not available",
                                ))
                            )
                            if not (capacity_error or model_unavailable):
                                raise
                    if body is None:
                        raise RuntimeError(
                            f"Основная модель {primary_model} и резервные модели недоступны. Последняя ошибка: {last_error}"
                        ) from last_error
            payload["model"] = model
            reply = self._extract(body)
            result_content = reply["content"]
            tool_calls = reply["tool_calls"]
            if not tool_calls or self.tool_executor is None or not active_tools:
                break
            messages.append({"role": "assistant", "content": reply["content"], "tool_calls": tool_calls})
            confirmation_pending = False
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                    output = self.tool_executor(fn.get("name", ""), args)
                except Exception as exc:
                    output = f"Ошибка выполнения инструмента: {exc}"
                output_text = str(output)[:2000]
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": output_text})
                if output_text.startswith(CONFIRMATION_PREFIX) and "требует подтверждения" in output_text:
                    result_content = output_text
                    confirmation_pending = True
                    break
            if confirmation_pending:
                break
            payload = {"model": model, "messages": messages, "temperature": 0.25}
            if active_tools:
                payload["tools"] = active_tools
        else:
            result_content = result_content or "Достигнут предел шагов агента."

        history_prompt = prompt.get("text", "") if isinstance(prompt, dict) else prompt
        self.history.append({"role": "user", "content": history_prompt})
        self.history.append({"role": "assistant", "content": result_content})
        if len(self.history) > MAX_HISTORY_MESSAGES * 2:
            del self.history[: len(self.history) - MAX_HISTORY_MESSAGES * 2]
        self.last_used_model = model
        return result_content
