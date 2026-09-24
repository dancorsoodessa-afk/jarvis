"""JARVIS task router: separate fast commands, reasoning, coding and additional models."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class RoleDecision:
    role: str
    reason: str

_RULES = {
    "coding": ("код", "кодить", "программ", "скрипт", "python", "powershell", "javascript",
               "typescript", "flutter", "android", "github", "git", "репозитор", "исправь ошиб",
               "исправить код", "напиши программу", "собери", "build", "debug", "отлад",
               "traceback", "exception", "api", "sql", "json", "yaml"),
    "reasoning": ("проанализ", "сложн", "почему", "разберись", "сравни", "спланируй", "план",
                  "архитектур", "исследован", "глубоко", "стратег", "причин", "риски",
                  "найди проблему", "диагност", "оптимиз", "как лучше"),
    "additional": ("второе мнение", "дополнитель", "перепроверь", "альтернатив", "другой взгляд",
                   "критик", "ревью"),
}

def classify_role(prompt: Any) -> RoleDecision:
    text = prompt.get("text", "") if isinstance(prompt, dict) else str(prompt or "")
    text = re.sub(r"\s+", " ", str(text).lower()).strip()
    for role in ("additional", "coding", "reasoning"):
        if any(token in text for token in _RULES[role]):
            return RoleDecision(role, f"профиль задачи: {role}")
    if any(token in text for token in ("открой", "запусти", "покажи", "найди файл", "громкость",
                                       "скриншот", "время", "погода", "напомни", "удали",
                                       "прочитай", "переведи", "посчитай", "привет", "спасибо")):
        return RoleDecision("fast", "обычная команда/быстрый ответ")
    if isinstance(prompt, dict):
        name = str((prompt.get("attachment") or {}).get("name") or "").lower()
        if name.endswith((".py",".js",".ts",".tsx",".jsx",".ps1",".bat",".cmd",".json",".yaml",".yml",".toml",".dart",".java",".cpp",".h")):
            return RoleDecision("coding", "прикреплён исходный код")
    return RoleDecision("fast", "обычный диалог")

def discover_chat_endpoint(endpoint: str, timeout: float = 2.0) -> tuple[str, list[str]]:
    """Check an OpenAI-compatible chat endpoint and discover models."""
    from urllib.parse import urlsplit, urlunsplit
    from urllib.request import Request, urlopen
    import json

    raw = str(endpoint or "").strip()
    if not raw:
        return "", []
    parts = urlsplit(raw)
    path = parts.path or ""
    if path.endswith("/chat/completions"):
        models_path = path[:-len("/chat/completions")] + "/models"
    elif path.endswith("/completions"):
        models_path = path[:-len("/completions")] + "/models"
    elif path.endswith("/models"):
        models_path = path
        path = path[:-len("/models")] + "/chat/completions"
    else:
        models_path = path.rstrip("/") + "/models"
        path = path.rstrip("/") + "/chat/completions"
    models_url = urlunsplit((parts.scheme, parts.netloc, models_path, parts.query, ""))
    chat_url = urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))
    request = Request(models_url, headers={"Accept": "application/json", "User-Agent": "JARVIS"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return "", []
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return "", []
    models = []
    for item in payload.get("data", []) if isinstance(payload, dict) else []:
        if isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))
    return chat_url, models

class RoleRouterProvider:
    name = "Джарвис ИИ"
    def __init__(self, providers: dict[str, Any], fallback_order=("fast","reasoning","coding","additional")):
        self.providers = providers
        self.fallback_order = fallback_order
        self.tool_executor = None
        self.last_role = "fast"
        self.last_reason = ""
        self.last_model = ""
    def generate(self, prompt, tools=None, max_steps=4) -> str:
        decision = classify_role(prompt)
        ordered = [decision.role] + [r for r in self.fallback_order if r != decision.role]
        errors = []
        for role in ordered:
            provider = self.providers.get(role)
            if provider is None:
                continue
            try:
                provider.tool_executor = self.tool_executor
                result = provider.generate(prompt, tools=tools, max_steps=max_steps)
                self.last_role, self.last_reason = role, decision.reason
                self.last_model = getattr(provider, "last_used_model", "") or getattr(provider, "model", "")
                return result
            except Exception as exc:
                errors.append(f"{role}: {exc}")
        raise RuntimeError("Все AI-модели недоступны. " + " | ".join(errors))
    @property
    def history(self):
        for provider in self.providers.values():
            if hasattr(provider, "history"):
                return provider.history
        return []
    @property
    def system_prompt(self):
        for provider in self.providers.values():
            if hasattr(provider, "system_prompt"):
                return provider.system_prompt
        return ""
    @system_prompt.setter
    def system_prompt(self, value):
        for provider in self.providers.values():
            if hasattr(provider, "system_prompt"):
                provider.system_prompt = value
