"""Free-only multi-agent coordinator for Буся.

The main agent is the final answerer. DeepSeek and GLM are independent
consultants when explicitly configured with free/local OpenAI-compatible
endpoints and model names. No paid provider is hard-coded.
"""
from __future__ import annotations

from typing import Callable, Optional

from .providers.openai_chat import OpenAIChatProvider


class ThreeAgentProvider:
    """Run a main model plus optional DeepSeek and GLM consultants."""

    name = "three-agent-free"

    def __init__(
        self,
        main: OpenAIChatProvider,
        deepseek: OpenAIChatProvider | None = None,
        glm: OpenAIChatProvider | None = None,
    ) -> None:
        self.main = main
        self.deepseek = deepseek
        self.glm = glm
        self.tool_executor: Optional[Callable] = None
        self.on_delta = None

    @staticmethod
    def _safe_generate(provider: OpenAIChatProvider | None, prompt: str) -> str | None:
        if provider is None:
            return None
        try:
            return provider.generate(prompt)
        except (RuntimeError, OSError, ValueError) as exc:
            return f"АГЕНТ НЕДОСТУПЕН: {exc}"

    def generate(self, prompt: str, tools: Optional[list] = None, max_steps: int = 4) -> str:
        self.main.tool_executor = self.tool_executor
        self.main.on_delta = self.on_delta

        deepseek = self._safe_generate(
            self.deepseek,
            "Ты дополнительный агент DeepSeek для Буси. "
            "Дай короткий технический и логический разбор запроса. "
            "Не выдумывай факты.\n\nЗапрос:\n" + prompt,
        )
        glm = self._safe_generate(
            self.glm,
            "Ты дополнительный агент GLM для Буси. "
            "Проверь запрос, факты и возможные ошибки независимо от основного агента. "
            "Не выдумывай факты.\n\nЗапрос:\n" + prompt,
        )

        consultants: list[str] = []
        if deepseek is not None:
            consultants.append("Мнение DeepSeek:\n" + deepseek)
        if glm is not None:
            consultants.append("Мнение GLM:\n" + glm)
        if consultants:
            synthesis = (
                "Запрос пользователя:\n" + prompt + "\n\n" + "\n\n".join(consultants)
                + "\n\nТы — основной агент Буся. Сформируй один точный ответ пользователю. "
                  "Проверяй противоречия между агентами. Отвечай по-русски."
            )
        else:
            synthesis = prompt
        return self.main.generate(synthesis, tools=tools, max_steps=max_steps)
