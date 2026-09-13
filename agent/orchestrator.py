"""JARVIS universal orchestration layer.

This module defines the separation between the dispatcher, the local Core,
cloud/vision/code/web specialists, MCP tools, memory, planner loop, safety
and the visual/voice surfaces. It deliberately does not hard-code an Ollama
model tag: the selected local Core model is configuration data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Role(str, Enum):
    DISPATCHER = "главный диспетчер"
    CORE = "универсальное ядро"
    CLOUD = "облачная модель"
    VISION = "зрение"
    CODE = "код"
    WEB = "веб-агент"
    MCP = "MCP"
    MEMORY = "память"
    LOOP = "планировщик"
    VOICE = "голос"
    VISUAL = "3D-визуализатор"


class ActionRisk(str, Enum):
    SAFE = "безопасно"
    CONFIRM = "требует подтверждения"
    BLOCK = "заблокировано"


DANGEROUS_ACTIONS = {
    "delete_file": ActionRisk.CONFIRM,
    "kill_process": ActionRisk.CONFIRM,
    "install_program": ActionRisk.CONFIRM,
    "system_settings": ActionRisk.CONFIRM,
    "send_message": ActionRisk.CONFIRM,
    "send_email": ActionRisk.CONFIRM,
    "purchase": ActionRisk.CONFIRM,
}


@dataclass
class TaskPlan:
    goal: str
    steps: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    status: str = "план"


@dataclass
class Orchestrator:
    """Deterministic control plane around model providers.

    The orchestrator does not replace the LLM. It decides which specialist is
    appropriate, keeps task state, applies the safety gate, and exposes hooks
    for the future MCP/web/vision/code/3D implementations.
    """

    core: Any = None
    cloud: Any = None
    vision: Any = None
    code: Any = None
    web: Any = None
    mcp: Any = None
    memory: Any = None
    loop: Any = None
    visual: Any = None
    voice: Any = None
    confirmation: Callable[[str], bool] | None = None

    def classify(self, request: str) -> Role:
        text = request.lower()
        if any(x in text for x in ("фото", "изображен", "картин", "скриншот", "видео")):
            return Role.VISION
        if any(x in text for x in ("код", "программа", "python", "исправь", "напиши скрипт")):
            return Role.CODE
        if any(x in text for x in ("найди в интернете", "поищи в интернете", "сайт", "новости", "веб")):
            return Role.WEB
        return Role.CORE

    def plan(self, goal: str, steps: list[str] | None = None) -> TaskPlan:
        return TaskPlan(goal=goal, steps=list(steps or []), status="готов к выполнению")

    def risk(self, action: str) -> ActionRisk:
        return DANGEROUS_ACTIONS.get(action, ActionRisk.SAFE)

    def authorize(self, action: str) -> bool:
        risk = self.risk(action)
        if risk is ActionRisk.SAFE:
            return True
        if risk is ActionRisk.BLOCK:
            return False
        return bool(self.confirmation and self.confirmation(action))

    def execute(self, request: str, handler: Callable[[str], str]) -> str:
        """Execute a prepared task through the selected handler.

        Higher-level planners may call this repeatedly after each verification
        step. The handler itself remains responsible for model/tool execution.
        """
        role = self.classify(request)
        target = {
            Role.CORE: self.core,
            Role.CLOUD: self.cloud,
            Role.VISION: self.vision,
            Role.CODE: self.code,
            Role.WEB: self.web,
            Role.MCP: self.mcp,
        }.get(role)
        _ = target  # provider selection is intentionally injectable
        return handler(request)
