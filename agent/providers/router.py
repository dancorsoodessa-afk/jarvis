"""Multi-model provider router for JARVIS."""
from __future__ import annotations

from typing import Optional

from .openai_chat import DEFAULT_SYSTEM_PROMPT, OpenAIChatProvider


class CloudRouterProvider:
    """Route normal, coding and fast requests to dedicated cloud models."""

    name = "главный диспетчер"

    def __init__(self, url: str, api_key: str, primary_model: str,
                 code_model: str, fast_model: str,
                 history: Optional[list] = None):
        self.url = url
        self.api_key = api_key
        self.primary_model = primary_model
        self.code_model = code_model
        self.fast_model = fast_model
        self.history = history if history is not None else []
        self.tool_executor = None
        self.on_delta = None
        self.last_route = "главный помощник"
        self.system_prompt = DEFAULT_SYSTEM_PROMPT

    @staticmethod
    def classify(prompt: str) -> str:
        text = prompt.lower()
        code = ("код", "программ", "python", "javascript", "typescript", "react",
                "next.js", "sql", "git", "github", "opencode", "debug", "ошибк",
                "исправь код", "напиши скрипт", "репозитор")
        fast = ("быстро", "коротко", "что такое", "переведи", "напомни", "время",
                "погода", "привет", "спасибо")
        if any(x in text for x in code):
            return "код"
        if any(x in text for x in fast) and len(text) < 180:
            return "быстрый"
        return "главный"

    def _provider(self, route: str):
        model = {"код": self.code_model, "быстрый": self.fast_model,
                 "главный": self.primary_model}[route]
        return OpenAIChatProvider(
            url=self.url, api_key=self.api_key, model=model,
            history=self.history, system_prompt=self.system_prompt,
        )

    def generate(self, prompt: str, tools=None, max_steps: int = 4) -> str:
        route = self.classify(prompt)
        self.last_route = route
        provider = self._provider(route)
        provider.tool_executor = self.tool_executor
        provider.on_delta = self.on_delta
        result = provider.generate(prompt, tools=tools, max_steps=max_steps)
        self.history[:] = provider.history
        return result
