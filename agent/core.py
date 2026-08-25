from dataclasses import dataclass
from typing import Protocol

from .tools.registry import ConfirmationRequired, ToolRegistry
from .memory.store import MemoryStore


class AIProvider(Protocol):
    name: str
    def generate(self, prompt: str) -> str: ...


@dataclass
class AgentResult:
    text: str
    provider: str
    tool_used: str | None = None
    needs_confirmation: bool = False


class JarvisAgent:
    def __init__(self, provider: AIProvider, tools: ToolRegistry | None = None,
                 memory: MemoryStore | None = None, reminders=None):
        self.provider = provider
        self.tools = tools or ToolRegistry()
        self.memory = memory
        self.reminders = reminders
        self._pending_tool: tuple[str, tuple, dict] | None = None

    def handle(self, message: str) -> AgentResult:
        text = message.strip()
        if not text:
            return AgentResult("Я здесь. Что нужно сделать?", self.provider.name)

        due = self._due_reminders()
        result = self._dispatch(text)
        if due:
            result.text = "⏰ " + "\n⏰ ".join(due) + "\n\n" + result.text
        return result

    def _due_reminders(self) -> list[str]:
        if self.reminders is None:
            return []
        try:
            return self.reminders.pop_due()
        except Exception:
            return []

    def _dispatch(self, text: str) -> AgentResult:
        if self._pending_tool:
            if text.lower() not in ("yes", "y", "да", "д"):
                self._pending_tool = None
                return AgentResult("Отменено.", self.provider.name)
            name, args, kwargs = self._pending_tool
            self._pending_tool = None
            try:
                output = self.tools.call(name, *args, _confirmed=True, **kwargs)
            except (ValueError, RuntimeError) as exc:
                return AgentResult(f"Ошибка инструмента «{name}»: {exc}",
                                   self.provider.name, tool_used=name)
            self._remember(text, str(output))
            return AgentResult(str(output), self.provider.name, tool_used=name)

        if text.startswith("/"):
            return self._handle_tool_command(text)

        reply = self.provider.generate(text)
        self._remember(text, reply)
        return AgentResult(reply, self.provider.name)

    def _handle_tool_command(self, text: str) -> AgentResult:
        parts = text[1:].split()
        name, args = parts[0], tuple(parts[1:])
        try:
            output = self.tools.call(name, *args)
        except ConfirmationRequired:
            self._pending_tool = (name, args, {})
            return AgentResult(
                f"Инструмент «{name}» требует подтверждения. Выполнить? (yes/да)",
                self.provider.name, tool_used=name, needs_confirmation=True,
            )
        except KeyError:
            return AgentResult(
                f"Неизвестный инструмент «{name}». Доступны: {', '.join(self.tools.names()) or '—'}",
                self.provider.name,
            )
        except (ValueError, RuntimeError) as exc:
            return AgentResult(f"Ошибка инструмента «{name}»: {exc}",
                               self.provider.name, tool_used=name)
        self._remember(text, str(output))
        return AgentResult(str(output), self.provider.name, tool_used=name)

    def _remember(self, user: str, assistant: str):
        if self.memory is None:
            return
        data = self.memory.load()
        history = data.setdefault("history", [])
        history.append({"user": user, "assistant": assistant})
        self.memory.save(data)
