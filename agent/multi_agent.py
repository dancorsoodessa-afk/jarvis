"""Free-only three-agent coordinator for Буся.

Agents:
  - main: the primary local/free model and final answerer;
  - deepseek: optional local/free DeepSeek model;
  - glm: optional local/free GLM model.

No paid provider or API is hard-coded. All agents use an OpenAI-compatible
local endpoint (normally Ollama/llama.cpp/LM Studio) and models are discovered
from /models when their model variable is empty.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .providers.openai_chat import OpenAIChatProvider


@dataclass
class AgentSlot:
    name: str
    provider: OpenAIChatProvider
    role: str


class ThreeAgentProvider:
    """Run a main model plus DeepSeek and GLM when locally available."""

    name = "three-agent-free"

    def __init__(
        self,
        main: OpenAIChatProvider,
        deepseek: OpenAIChatProvider,
        glm: OpenAIChatProvider,
    ) -> None:
        self.main = main
        self.deepseek = deepseek
        self.glm = glm
        self.tool_executor: Optional[Callable] = None
        self.on_delta = None

    @staticmethod
    def _safe_generate(provider: OpenAIChatProvider, prompt: str) -> str:
        try:
            return provider.generate(prompt)
        except (RuntimeError, OSError, ValueError) as exc:
            return f"АГЕНТ НЕДОСТУПЕН: {exc}"

    def generate(self, prompt: str, tools: Optional[list] = None, max_steps: int = 4) -> str:
        # Main is always the final decision/answer model. Secondary agents are
        # consultants; their failure never prevents the main local agent from answering.
        self.main.tool_executor = self.tool_executor
        self.main.on_delta = self.on_delta

        deepseek_prompt = (
            "Ты дополнительный агент DeepSeek для Буси. "
            "Дай короткий технический/логический разбор запроса. "
            "Не выполняй опасных действий и не выдумывай факты.\n\nЗапрос:\n" + prompt
        )
        glm_prompt = (
            "Ты дополнительный агент GLM для Буси. "
            "Дай независимую проверку запроса, фактов и возможных ошибок. "
            "Не выдумывай факты.\n\nЗапрос:\n" + prompt
        )
        deepseek = self._safe_generate(self.deepseek, deepseek_prompt)
        glm = self._safe_generate(self.glm, glm_prompt)

        synthesis = (
            "Запрос пользователя:\n"
            + prompt
            + "\n\nМнение дополнительного агента DeepSeek:\n"
            + deepseek
            + "\n\nМнение дополнительного агента GLM:\n"
            + glm
            + "\n\nТы — основной агент Буся. Сформируй один точный ответ пользователю. "
              "Проверяй противоречия между агентами. Не упоминай внутреннюю кухню, "
              "если это не нужно для ответа. Отвечай по-русски."
        )
        return self.main.generate(synthesis, tools=tools, max_steps=max_steps)
