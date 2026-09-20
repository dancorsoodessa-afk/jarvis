"""Провайдер чата для OpenAI-совместимых API."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_SYSTEM_PROMPT = (
    "Ты — Джарвис, персональный ИИ-ассистент пользователя. "
    "Всегда отвечай на русском языке, если пользователь явно не попросил другой язык. "
    "Названия инструментов, кнопок, действий и подсказок формулируй на русском языке. "
    "Если задача требует инструмента — используй доступный инструмент самостоятельно. Для команд «сделай громче/тише», «прибавь/убавь звук» используй change_volume с delta +10/-10, не проси пользователя менять громкость вручную. "
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
                 system_prompt: Optional[str] = None):
        self.url = (url or os.environ.get("JARVIS_CHAT_URL", "")).strip()
        configured_key = api_key if api_key is not None else os.environ.get("JARVIS_CHAT_KEY", "")
        self.api_key = (configured_key or os.environ.get("OPENROUTER_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")).strip()
        self.model = (model or os.environ.get("JARVIS_CHAT_MODEL", "")).strip()
        self.timeout = timeout
        self.history: list[dict] = history if history is not None else []
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.tool_executor = None
        self.on_delta = None
        self._discovered_model: str | None = None

    def _ensure_endpoint(self) -> None:
        if self.url:
            return
        from agent.core_router import discover_chat_endpoint
        self.url, models = discover_chat_endpoint()
        if not self.model and models:
            self._discovered_model = models[0]

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
        # OpenRouter's free router is a real model slug. Do not replace it
        # with a hard-coded model that may have no available endpoint.
        return model.strip()

    def _auth_headers(self, *, stream: bool = False) -> dict:
        if not self.api_key:
            parsed = urllib.parse.urlsplit(self.url)
            if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
                raise RuntimeError(
                    "API-ключ не задан. Для удалённого ИИ укажите API key в настройках JARVIS."
                )
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        if stream:
            headers["Accept"] = "text/event-stream"
        return headers

    def _request(self, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url, data=data, headers=self._auth_headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Ошибка API: HTTP {exc.code}. {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Не удалось подключиться к ИИ: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("ИИ вернул некорректный JSON-ответ") from exc

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
        req = urllib.request.Request(self.url, data=data, headers=self._auth_headers(stream=True))
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
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Ошибка API: HTTP {exc.code}. {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Не удалось подключиться к ИИ: {exc.reason}") from exc
        msg: dict = {"role": "assistant", "content": "".join(content_parts)}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return {"choices": [{"message": msg}]}

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
        return result_content
