"""JARVIS Core routing: local Qwen 3 8B first, cloud only by explicit configuration."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CoreSelection:
    provider: str
    model: str
    source: str


def _models_endpoint(chat_url: str) -> str:
    base = chat_url.rstrip("/")
    marker = "/v1/chat/completions"
    if base.endswith(marker):
        return base[: -len(marker)] + "/v1/models"
    if base.endswith("/v1"):
        return base + "/models"
    return base + "/v1/models"


def discover_local_qwen3_8b(chat_url: str, timeout: float = 1.5) -> str:
    """Return the installed Qwen 3 8B model tag from a local OpenAI-compatible server.

    No model tag is guessed. If the exact family/size is not exposed by the server,
    the error contains the models that were actually returned.
    """
    url = _models_endpoint(chat_url)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    models = [str(item.get("id", "")).strip() for item in payload.get("data", []) if item.get("id")]
    matches = [m for m in models if "qwen3" in m.lower() and "8b" in m.lower()]
    if not matches:
        raise RuntimeError(
            "Локальное ядро Qwen 3 8B не найдено. Сервер сообщил модели: "
            + (", ".join(models) if models else "список пуст")
        )
    return sorted(matches, key=lambda value: (":" not in value, len(value)))[0]


def select_core(provider: str, chat_url: str, configured_model: str = "") -> CoreSelection:
    """Select the main reasoning model without silently substituting another model."""
    provider = (provider or "openai-compatible").strip().lower()
    configured_model = (configured_model or "").strip()
    if provider == "openai-compatible" and "127.0.0.1:11434" in chat_url:
        model = configured_model or discover_local_qwen3_8b(chat_url)
        return CoreSelection(provider=provider, model=model, source="Локально / Qwen 3 8B")
    if not configured_model:
        raise RuntimeError("Для облачного провайдера не задана модель JARVIS_CHAT_MODEL.")
    return CoreSelection(provider=provider, model=configured_model, source="Облачный провайдер")
