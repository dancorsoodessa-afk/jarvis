"""JARVIS core routing helpers for OpenAI-compatible and local runtimes."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .config import normalize_provider


@dataclass(frozen=True)
class CoreSelection:
    provider: str
    model: str
    source: str


# Common local OpenAI-compatible endpoints. The explicit environment URL always wins.
LOCAL_BACKEND_CANDIDATES = (
    "http://127.0.0.1:1234/v1/chat/completions",  # LM Studio / compatible local runtimes
    "http://127.0.0.1:11434/v1/chat/completions",  # Ollama compatibility API
    "http://127.0.0.1:8080/v1/chat/completions",  # common local servers
    "http://127.0.0.1:8000/v1/chat/completions",
    "http://127.0.0.1:10000/v1/chat/completions",  # llama.cpp server
    "http://127.0.0.1:9119/v1/chat/completions",  # local AI server stacks
)


def _models_endpoint(chat_url: str) -> str:
    parsed = urllib.parse.urlsplit(chat_url.rstrip("/"))
    path = parsed.path
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")] + "/models"
    elif path.endswith("/v1"):
        path += "/models"
    elif not path.endswith("/models"):
        path = path.rstrip("/") + "/v1/models"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _probe_models(chat_url: str, timeout: float = 1.5) -> list[str]:
    url = _models_endpoint(chat_url)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data", []) if isinstance(payload, dict) else []
    return [str(item.get("id", "")).strip() for item in data if isinstance(item, dict) and str(item.get("id", "")).strip()]


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def discover_chat_endpoint(preferred_url: str = "", timeout: float = 1.5) -> tuple[str, list[str]]:
    """Return the configured OpenRouter endpoint, or a preferred compatible endpoint."""
    preferred = preferred_url.strip()
    if preferred and "openrouter.ai" not in preferred:
        try:
            models = _probe_models(preferred, timeout=timeout)
            if models:
                return preferred, models
        except Exception:
            pass
    return OPENROUTER_ENDPOINT, []


def discover_model(chat_url: str, timeout: float = 3.0) -> str:
    """Return the first model actually exposed by an OpenAI-compatible server."""
    url = _models_endpoint(chat_url)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Не удалось получить список моделей: HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Сервер моделей недоступен: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Сервер моделей вернул некорректный JSON") from exc
    models = [str(item.get("id", "")).strip() for item in payload.get("data", []) if isinstance(item, dict)]
    models = [m for m in models if m]
    if not models:
        raise RuntimeError("OpenAI-compatible сервер не сообщил доступных моделей.")
    return models[0]


def discover_local_qwen3_8b(chat_url: str, timeout: float = 3.0) -> str:
    """Backward-compatible helper; require an actual Qwen 3 8B model if requested."""
    models_url = _models_endpoint(chat_url)
    req = urllib.request.Request(models_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    models = [str(item.get("id", "")).strip() for item in payload.get("data", []) if isinstance(item, dict) and item.get("id")]
    matches = [m for m in models if "qwen3" in m.lower() and "8b" in m.lower()]
    if not matches:
        raise RuntimeError("Qwen 3 8B не найден. Доступные модели: " + (", ".join(models) if models else "нет"))
    return sorted(matches, key=lambda value: (":" not in value, len(value)))[0]


def select_core(provider: str, chat_url: str, configured_model: str = "") -> CoreSelection:
    """Select a model without assuming a specific vendor or model family."""
    provider = normalize_provider(provider)
    configured_model = (configured_model or "").strip()
    if provider == "local-vulkan":
        return CoreSelection(provider=provider, model=configured_model, source="Локально / llama.cpp + Vulkan")
    if provider != "openai-compatible":
        raise RuntimeError(f"Неизвестный провайдер: {provider}. Доступны: openai-compatible, local-vulkan")
    endpoint, models = discover_chat_endpoint(chat_url)
    return CoreSelection(provider=provider, model=configured_model or (models[0] if models else "openrouter/free"), source=f"OpenRouter: {endpoint}")
