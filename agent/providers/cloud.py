"""OpenAI-compatible chat provider (works with OpenAI, OpenRouter,
Groq, local llama.cpp server, etc.).

Config via environment variables:
  JARVIS_CLOUD_URL   e.g. https://api.openai.com/v1/chat/completions
  JARVIS_CLOUD_KEY   API key (sent as Bearer token)
  JARVIS_CLOUD_MODEL e.g. gpt-4o-mini
"""

import json
import os
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_SYSTEM_PROMPT = (
    "Ты — Джарвис, персональный AI-ассистент пользователя. "
    "У тебя есть инструменты для управления компьютером. "
    "Если задача требует инструмента — вызывай его, не проси пользователя "
    "делать это вручную. Отвечай кратко, по делу и на языке пользователя."
)

MAX_HISTORY_MESSAGES = 20


class OpenAIChatProvider:
    name = "cloud"

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, timeout: int = 60,
                 history: Optional[list] = None,
                 system_prompt: Optional[str] = None):
        self.url = url or os.environ.get("JARVIS_CLOUD_URL", "")
        self.api_key = api_key or os.environ.get("JARVIS_CLOUD_KEY", "")
        self.model = model or os.environ.get("JARVIS_CLOUD_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        # Shared, mutable message history (persisted by the agent's memory).
        self.history: list[dict] = history if history is not None else []
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        # Optional callable(name, args_dict) -> str used for function calling.
        self.tool_executor = None
        # Optional callable(delta_text) for streaming tokens to the UI.
        self.on_delta = None

    # -- internals ---------------------------------------------------------

    def _messages(self, prompt: str) -> list[dict]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history[-MAX_HISTORY_MESSAGES:])
        messages.append({"role": "user", "content": prompt})
        return messages

    def _request(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Cloud API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cloud API недоступен: {exc.reason}") from exc

    def _request_stream(self, payload: dict) -> dict:
        """Streaming request (SSE). Emits deltas via self.on_delta and
        returns the same shape as _request: {'choices': [{'message': ...}]}"""
        data = json.dumps({**payload, "stream": True}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=data, headers=headers)
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        piece = json.loads(chunk)["choices"][0].get("delta", {})
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    delta = piece.get("content") or ""
                    if delta:
                        content_parts.append(delta)
                        try:
                            self.on_delta(delta)
                        except Exception:
                            pass
                    for tc in piece.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "type": "function",
                                               "function": {"name": "", "arguments": ""}})
                        dst = tool_calls[idx]
                        if tc.get("id"):
                            dst["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            dst["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            dst["function"]["arguments"] += fn["arguments"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Cloud API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cloud API недоступен: {exc.reason}") from exc
        msg: dict = {"role": "assistant", "content": "".join(content_parts)}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        return {"choices": [{"message": msg}]}

    def _extract(self, body: dict) -> dict:
        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Неожиданный ответ Cloud API: {body!r}") from exc
        return {
            "content": msg.get("content") or "",
            "tool_calls": msg.get("tool_calls") or [],
        }

    # -- public API ---------------------------------------------------------

    def generate(self, prompt: str, tools: Optional[list] = None,
                 max_steps: int = 6) -> str:
        """Chat completion with a ReAct loop: if the model requests tool
        calls, execute them via `self.tool_executor` and keep going until
        it produces a final answer or max_steps is reached."""
        if not self.url:
            raise RuntimeError(
                "Cloud provider not configured: set JARVIS_CLOUD_URL "
                "(or run with JARVIS_LOCAL=1 for local inference)"
            )
        messages = self._messages(prompt)
        payload = {"model": self.model, "messages": messages,
                   "temperature": 0.7}
        if tools:
            payload["tools"] = tools

        result_content = ""
        for _ in range(max_steps):
            if self.on_delta is not None and "tools" in payload:
                body = self._request_stream(payload)
            else:
                body = self._request(payload)
            reply = self._extract(body)
            result_content = reply["content"]
            tool_calls = reply["tool_calls"]
            if not tool_calls or self.tool_executor is None:
                break
            # Record the assistant turn that requested the tools.
            messages.append({"role": "assistant",
                             "content": reply["content"],
                             "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                    output = self.tool_executor(fn.get("name", ""), args)
                except Exception as exc:
                    output = f"Ошибка: {exc}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": str(output)[:2000],
                })
        else:
            result_content = result_content or "Достигнут лимит шагов агента."

        # Persist the original question and the final answer only.
        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": result_content})
        if len(self.history) > MAX_HISTORY_MESSAGES * 2:
            del self.history[: len(self.history) - MAX_HISTORY_MESSAGES * 2]
        return result_content
