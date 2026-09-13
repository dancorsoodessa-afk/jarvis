"""Unified JARVIS orchestration layer."""
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
    """Single control plane connecting all JARVIS capabilities."""
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
    max_loop_steps: int = 8
    last_role: Role = Role.CORE
    last_action: str = ""

    def classify(self, request: str) -> Role:
        text = request.lower()
        if any(x in text for x in ("фото", "изображен", "картин", "скриншот", "видео", "что на картинке")):
            return Role.VISION
        if any(x in text for x in ("код", "программа", "python", "javascript", "git", "репозитор", "исправь")):
            return Role.CODE
        if any(x in text for x in ("mcp", "инструмент сервера", "mcp-сервер")):
            return Role.MCP
        if any(x in text for x in ("найди в интернете", "поищи в интернете", "сайт", "новости", "веб", "погода")):
            return Role.WEB
        return Role.CORE

    def plan(self, goal: str, steps: list[str] | None = None) -> TaskPlan:
        if steps is None:
            steps = ["понять задачу", "выполнить действие", "проверить результат"]
        return TaskPlan(goal=goal, steps=list(steps), status="готов к выполнению")

    def risk(self, action: str) -> ActionRisk:
        return DANGEROUS_ACTIONS.get(action, ActionRisk.SAFE)

    def authorize(self, action: str) -> bool:
        risk = self.risk(action)
        if risk is ActionRisk.SAFE:
            return True
        if risk is ActionRisk.BLOCK:
            return False
        return bool(self.confirmation and self.confirmation(action))

    def target(self, role: Role) -> Any:
        return {
            Role.CORE: self.core,
            Role.CLOUD: self.cloud,
            Role.VISION: self.vision,
            Role.CODE: self.code,
            Role.WEB: self.web,
            Role.MCP: self.mcp,
            Role.MEMORY: self.memory,
            Role.LOOP: self.loop,
            Role.VISUAL: self.visual,
            Role.VOICE: self.voice,
        }.get(role)

    def execute(self, request: str, handler: Callable[[str], str] | None = None) -> str:
        role = self.classify(request)
        self.last_role = role
        self.last_action = request
        if handler is not None:
            return handler(request)
        target = self.target(role)
        if target is None:
            raise RuntimeError(f"Модуль «{role.value}» не подключён")
        method = getattr(target, "execute", None) or getattr(target, "handle", None)
        if method is None:
            raise RuntimeError(f"Модуль «{role.value}» не имеет метода выполнения")
        return str(method(request))

    def run_loop(self, goal: str, step: Callable[[str, int], tuple[bool, str]]) -> list[str]:
        """Run bounded plan/act/check iterations; never loops indefinitely."""
        plan = self.plan(goal)
        outputs: list[str] = []
        for index, item in enumerate(plan.steps[: self.max_loop_steps], 1):
            done, output = step(item, index)
            outputs.append(str(output))
            if done:
                plan.status = "завершён"
                break
        else:
            plan.status = "остановлен по лимиту шагов"
        return outputs
