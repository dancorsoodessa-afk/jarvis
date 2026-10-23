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
        failed_backends = set()
        for role in ordered:
            provider = self.providers.get(role)
            if provider is None:
                continue
            # Several role profiles often point to the same URL/key. A DNS,
            # connection, authentication, or exhausted-credit error cannot be
            # fixed by retrying that same backend with three different models.
            backend = (
                str(getattr(provider, "url", "") or "").strip().rstrip("/"),
                str(getattr(provider, "api_key", "") or "").strip(),
            )
            if backend in failed_backends:
                errors.append(f"{role}: пропущен — этот API уже сообщил об ошибке подключения/доступа")
                continue
            try:
                provider.tool_executor = self.tool_executor
                result = provider.generate(prompt, tools=tools, max_steps=max_steps)
                self.last_role, self.last_reason = role, decision.reason
                self.last_model = getattr(provider, "last_used_model", "") or getattr(provider, "model", "")
                return result
            except Exception as exc:
                errors.append(f"{role}: {exc}")
                message = str(exc).lower()
                # All role profiles currently share the same Gemini endpoint and key.
                # Do not spend minutes retrying the same unavailable backend through
                # each role after an HTTP failure; let the UI recover promptly.
                http_failure = any(f"http {code}" in message for code in (
                    400, 401, 403, 404, 408, 409, 429, 500, 502, 503, 504
                ))
                backend_unavailable = (
                    "не удалось подключиться к ии" in message
                    or "не удалось подключиться к серверу моделей" in message
                    or "не удалось подключиться к серверу" in message
                    or "временно перегружен" in message
                    or "временно недоступен" in message
                    or http_failure
                )
                if backend_unavailable:
                    failed_backends.add(backend)
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
