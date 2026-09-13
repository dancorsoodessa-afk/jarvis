"""JARVIS system layers: dispatcher, planning loop, safety, memory, web/MCP, and avatar state."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable


RUSSIAN_STATES = {
    "idle": "ОЖИДАНИЕ",
    "listening": "СЛУШАЮ",
    "thinking": "РАССУЖДАЮ",
    "planning": "ПЛАНИРУЮ",
    "executing": "ВЫПОЛНЯЮ",
    "verifying": "ПРОВЕРЯЮ",
    "speaking": "ОТВЕЧАЮ",
    "confirmation": "ПОДТВЕРЖДЕНИЕ",
    "focus": "ФОКУС",
    "error": "ОШИБКА",
    "exiting": "ЗАВЕРШЕНИЕ",
}


@dataclass
class AvatarStateBus:
    state: str = "idle"
    action: str = "Ожидание"
    detail: str = ""
    listeners: list[Callable[[str, str, str], None]] = field(default_factory=list)

    def set(self, state: str, action: str = "", detail: str = "") -> None:
        if state not in RUSSIAN_STATES:
            state = "error"
        self.state, self.action, self.detail = state, action or RUSSIAN_STATES[state], detail
        for listener in tuple(self.listeners):
            try:
                listener(self.state, self.action, self.detail)
            except Exception:
                pass

    def subscribe(self, listener: Callable[[str, str, str], None]) -> None:
        self.listeners.append(listener)


class SafetyGate:
    """Central safety policy. Dangerous operations never run silently."""

    DANGEROUS = {
        "delete", "kill", "launch", "install", "uninstall", "system_settings",
        "send", "publish", "upload", "shutdown", "restart", "format",
    }

    def requires_confirmation(self, tool_name: str) -> bool:
        return tool_name.strip().lower() in self.DANGEROUS

    def explain(self, tool_name: str) -> str:
        return f"Действие «{tool_name}» может изменить систему или отправить данные. Требуется подтверждение пользователя."


@dataclass
class PlanStep:
    title: str
    action: Callable[[], Any]
    verify: Callable[[Any], bool] | None = None


@dataclass
class PlanResult:
    success: bool
    results: list[Any]
    failed_step: str | None = None
    message: str = ""


class PlannerLoop:
    """Bounded plan → execute → verify loop; prevents uncontrolled autonomous loops."""

    def __init__(self, max_steps: int = 8):
        self.max_steps = max(1, max_steps)

    def run(self, steps: Iterable[PlanStep], on_state: Callable[[str, str], None] | None = None) -> PlanResult:
        results: list[Any] = []
        for index, step in enumerate(steps):
            if index >= self.max_steps:
                return PlanResult(False, results, step.title, "Достигнут предел шагов плана.")
            if on_state:
                on_state("executing", step.title)
            try:
                value = step.action()
            except Exception as exc:
                return PlanResult(False, results, step.title, f"Ошибка шага: {exc}")
            results.append(value)
            if step.verify is not None:
                if on_state:
                    on_state("verifying", step.title)
                try:
                    verified = bool(step.verify(value))
                except Exception as exc:
                    return PlanResult(False, results, step.title, f"Ошибка проверки: {exc}")
                if not verified:
                    return PlanResult(False, results, step.title, "Проверка результата не пройдена.")
        return PlanResult(True, results, message="План выполнен и проверен.")


class LocalVectorMemory:
    """Small dependency-free local vector store using deterministic hashed embeddings.

    It is intentionally a storage layer, not a claim of model-quality semantic search.
    If a real embedding service is added later, vectors can be replaced without changing the API.
    """

    def __init__(self, path: str | Path, dimensions: int = 256):
        self.path = str(path)
        self.dimensions = dimensions
        self._lock = threading.Lock()
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, text TEXT NOT NULL, vector BLOB NOT NULL, created REAL NOT NULL)")
            db.commit()

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if t]
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "little") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def add(self, text: str) -> int:
        vector = json.dumps(self._embed(text), separators=(",", ":")).encode("utf-8")
        with self._lock, sqlite3.connect(self.path) as db:
            cur = db.execute("INSERT INTO memories(text, vector, created) VALUES(?,?,?)", (text, vector, time.time()))
            db.commit()
            return int(cur.lastrowid)

    def search(self, query: str, limit: int = 5) -> list[str]:
        q = self._embed(query)
        with self._lock, sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT text, vector FROM memories ORDER BY created DESC LIMIT 5000").fetchall()
        scored = []
        for text, raw in rows:
            try:
                vector = json.loads(raw.decode("utf-8"))
                score = sum(a * b for a, b in zip(q, vector))
                scored.append((score, text))
            except Exception:
                continue
        scored.sort(reverse=True)
        return [text for score, text in scored[: max(0, limit)] if score > 0]


class WebAgent:
    """Dedicated web layer. It is separate from the reasoning core and can be replaced."""

    def __init__(self, search: Callable[[str], Any]):
        self._search = search

    def search(self, query: str) -> Any:
        return self._search(query)


class MCPToolLayer:
    """MCP boundary for future/connected servers without coupling the core to one vendor."""

    def __init__(self):
        self.servers: dict[str, Any] = {}

    def register(self, name: str, server: Any) -> None:
        self.servers[name] = server

    def names(self) -> list[str]:
        return sorted(self.servers)


class JarvisSystem:
    """Administrator above the individual JARVIS subsystems."""

    def __init__(self, agent, memory_path: str, web_search: Callable[[str], Any]):
        self.agent = agent
        self.provider = agent.provider
        self.tools = agent.tools
        self.memory = agent.memory
        self.voice = None
        self.vision = None
        self.web = WebAgent(web_search)
        self.mcp = MCPToolLayer()
        self.planner = PlannerLoop()
        self.safety = SafetyGate()
        self.avatar = AvatarStateBus()
        self.vector_memory = LocalVectorMemory(Path(memory_path).with_suffix(".vectors.db"))

    def handle(self, message: str):
        self.avatar.set("thinking", "Разбираю запрос")
        try:
            self.vector_memory.add(message)
            result = self.agent.handle(message)
            self.avatar.set("speaking", "Формирую ответ")
            return result
        except Exception:
            self.avatar.set("error", "Ошибка выполнения")
            raise
