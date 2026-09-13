"""JARVIS web-agent service built on the existing network tools."""
from __future__ import annotations

from dataclasses import dataclass

from .tools import web


@dataclass
class WebAgent:
    """Small deterministic web worker exposed to the orchestrator and tools."""

    max_results: int = 5

    def search(self, query: str) -> str:
        return web.web_search(query)

    def weather(self, city: str) -> str:
        return web.weather(city)

    def execute(self, request: str) -> str:
        """Interpret a simple web request without invoking an LLM recursively."""
        text = request.strip()
        lower = text.lower()
        if any(token in lower for token in ("погода", "weather")):
            city = text
            for marker in ("погода в", "погода", "weather in", "weather"):
                if marker in lower:
                    city = text[lower.index(marker) + len(marker):].strip(" :,-")
                    break
            if not city:
                raise ValueError("Укажите город для погоды")
            return self.weather(city)
        return self.search(text)
