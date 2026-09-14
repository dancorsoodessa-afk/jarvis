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
    "Если задача требует инструмента — используй доступный инструмент самостоятельно. "
    "Не заставляй пользователя выполнять действие вручную, если ты можешь выполнить его инструментом. "
    "Перед опасным действием дождись явного подтверждения пользователя. "
    "Отвечай понятно, кратко и по делу. Не выдумывай результат: если действие не выполнено или недоступно, прямо сообщи об этом."
)

MAX_HISTORY_MESSAGES = 12


class OpenAIChatProvider:
    name = "Джарвис ИИ"

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, timeout: int = 30,
                 history: Optional[list] = None,
                 system_prompt: Optional[str] = None):
        self.url = (url or os.environ.get("JARVIS_CHAT_URL", "")).strip()
        self.api_key = api_key if api_key is not None else os.environ.get("JARVIS_CHAT_KEY", "")
        self.model = (model or os.environ.get("JARVIS_CHAT_MODEL", "")).strip()
        self.timeout = timeout
        self.history: list[dict] = history if history is not None else []
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.tool_executor = None
        self.on_delta = None
        self._discovered_model: str | None = None

    def _messages(self, prompt: str) -> list[dict]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history[-MAX_HISTORY_MESSAGES:])
        messages.append({"role": "user", "content": prompt})
        return messages

    def _request(self, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=data, headers=headers)
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
        """Discover the first model exposed by an OpenAI-compatible server."""
        if self.model:
            return self.model
        if self._discovered_model:
            return self._discovered_model
        url = self._models_url()
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, headers=headers)
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
        return self._discovered_model

    def _request_stream(self, payload: dict) -> dict:
        data = json.dumps({**payload, "stream": True}, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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

    def generate(self, prompt: str, tools: Optional[list] = None, max_steps: int = 4) -> str:
        if not self.url:
            raise RuntimeError("ИИ не настроен: укажите адрес API в настройках")
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
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                    output = self.tool_executor(fn.get("name", ""), args)
                except Exception as exc:
                    output = f"Ошибка выполнения инструмента: {exc}"
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": str(output)[:2000]})
            payload = {"model": model, "messages": messages, "temperature": 0.25}
            if tools:
                payload["tools"] = tools
        else:
            result_content = result_content or "Достигнут предел шагов агента."

        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": result_content})
        if len(self.history) > MAX_HISTORY_MESSAGES * 2:
            del self.history[: len(self.history) - MAX_HISTORY_MESSAGES * 2]
        return result_content
