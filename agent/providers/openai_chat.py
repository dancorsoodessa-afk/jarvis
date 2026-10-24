"""Провайдер чата для OpenAI-совместимых API."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import time
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
CONFIRMATION_PREFIX = "Инструмент «"


class OpenAIChatProvider:
    name = "Джарвис ИИ"

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, timeout: int = 30,
                 history: Optional[list] = None,
                 system_prompt: Optional[str] = None, fallback_models: Optional[list[str]] = None):
        self.url = (url or os.environ.get("JARVIS_CHAT_URL", "")).strip()
        configured_key = api_key if api_key is not None else os.environ.get("JARVIS_CHAT_KEY", "")
        self.api_key = (configured_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        self.model = (model or os.environ.get("JARVIS_CHAT_MODEL", "")).strip()
        self.timeout = timeout
        self.history: list[dict] = history if history is not None else []
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.tool_executor = None
        self.on_delta = None
        self._discovered_model: str | None = None
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
        for attempt in range(4):
            req = urllib.request.Request(self.url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code in retryable and attempt < 3:
                    time.sleep(1.0 * (2 ** attempt))
                    continue
                if exc.code == 503:
                    raise RuntimeError(f"{self._provider_name()} временно перегружен (HTTP 503). Повторите запрос через минуту. " + detail) from exc
                raise RuntimeError(f"Ошибка API: HTTP {exc.code}. {detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < 3:
                    time.sleep(1.0 * (2 ** attempt))
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

    def health_check(self) -> str:
        """Actively verify credentials and endpoint reachability without generating tokens."""
        self._ensure_endpoint()
        url = self._models_url()
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 12)) as response:
                body = json.loads(response.read().decode("utf-8"))
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise RuntimeError("Провайдер ответил, но формат списка моделей неожиданный.")
            available = {
                str(item.get("id", "")).strip()
                for item in body["data"]
                if isinstance(item, dict) and item.get("id")
            }
            if self.model and available and self.model not in available:
                raise RuntimeError(f"Модель {self.model} отсутствует в списке доступных моделей этого ключа.")
            return "ONLINE"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:250]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Сеть недоступна: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Провайдер вернул некорректный JSON.") from exc

    def discover_model(self) -> str:
        if self.model:
            return self._normalize_model(self.model)
        if self._discovered_model:
            return self._normalize_model(self._discovered_model)
        self._ensure_endpoint()
        if self._discovered_model:
            return self._normalize_model(self._discovered_model)
        url = self._models_url()
        req = urllib.request.Request(url, headers={"Accept": "application/json", "Authorization": f"Bearer {self.api_key}"} if self.api_key else {"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 10)) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Не удалось получить список моделей: HTTP {exc.code}. {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Не удалось подключиться к серверу моделей: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Сервер моделей вернул некорректный JSON") from exc
        models = body.get("data") if isinstance(body, dict) else None
        ids = [str(item.get("id", "")).strip() for item in (models or []) if isinstance(item, dict)]
        ids = [item for item in ids if item]
        if not ids:
            raise RuntimeError(
                "Сервер ИИ доступен, но не сообщил ни одной модели. "
                "Укажите JARVIS_CHAT_MODEL вручную или запустите модель на сервере.")
        self._discovered_model = ids[0]
        return self._normalize_model(self._discovered_model)

    def _request_stream(self, payload: dict) -> dict:
        data = json.dumps({**payload, "stream": True}, ensure_ascii=False).encode("utf-8")
        headers = self._auth_headers(stream=True)
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(4):
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
                if exc.code in retryable and attempt < 3:
                    time.sleep(1.0 * (2 ** attempt))
                    continue
                if exc.code == 503:
                    raise RuntimeError(f"{self._provider_name()} временно перегружен (HTTP 503). Повторите запрос через минуту. " + detail) from exc
                raise RuntimeError(f"Ошибка API: HTTP {exc.code}. {detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < 3:
                    time.sleep(1.0 * (2 ** attempt))
                    continue
                raise RuntimeError(f"Не удалось подключиться к ИИ: {exc.reason}") from exc
        raise RuntimeError(f"{self._provider_name()} временно недоступен после нескольких попыток.")

    def _extract(self, body: dict) -> dict:
        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"ИИ вернул неожиданный ответ: {body!r}") from exc
        return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or []}

    def generate(self, prompt, tools: Optional[list] = None, max_steps: int = 4) -> str:
        self._ensure_endpoint()
        model = self.discover_model()
        messages = self._messages(prompt)
        payload = {"model": model, "messages": messages, "temperature": 0.25}
        if tools:
            payload["tools"] = tools

        result_content = ""
        for _ in range(max_steps):
            body = self._request_stream(payload) if self.on_delta is not None and "tools" in payload else self._request(payload)
            reply = self._extract(body)
            result_content = reply["content"]
            tool_calls = reply["tool_calls"]
            if not tool_calls or self.tool_executor is None:
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
            if tools:
                payload["tools"] = tools
        else:
            result_content = result_content or "Достигнут предел шагов агента."

        history_prompt = prompt.get("text", "") if isinstance(prompt, dict) else prompt
        self.history.append({"role": "user", "content": history_prompt})
        self.history.append({"role": "assistant", "content": result_content})
        if len(self.history) > MAX_HISTORY_MESSAGES * 2:
            del self.history[: len(self.history) - MAX_HISTORY_MESSAGES * 2]
        self.last_used_model = model
        return result_content
