from dataclasses import dataclass
from typing import Protocol
import logging

from .tools.registry import ConfirmationRequired, ToolRegistry
from .memory.store import MemoryStore

logger = logging.getLogger("jarvis.core")


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
        logger.debug("JarvisAgent initialized")

    def handle(self, message: str) -> AgentResult:
        text = message.strip()
        if not text:
            logger.debug("Empty message - greeting")
            return AgentResult("Я здесь. Что нужно сделать?", self.provider.name)

        logger.info(f"Handling message (length={len(text)})")
        due = self._due_reminders()
        result = self._dispatch(text)
        if due:
            result.text = "⏰ " + "\n⏰ ".join(due) + "\n\n" + result.text
        return result

    def _due_reminders(self) -> list[str]:
        if self.reminders is None:
            return []
        try:
            reminders = self.reminders.pop_due()
            if reminders:
                logger.info(f"Due reminders: {len(reminders)}")
            return reminders
        except Exception as e:
            logger.error(f"Error fetching reminders: {e}", exc_info=True)
            return []

    def _dispatch(self, text: str) -> AgentResult:
        if self._pending_tool:
            if text.lower() not in ("yes", "y", "да", "д"):
                self._pending_tool = None
                logger.debug("Tool confirmation declined")
                return AgentResult("Отменено.", self.provider.name)
            name, args, kwargs = self._pending_tool
            self._pending_tool = None
            try:
                logger.info(f"Executing confirmed tool: {name}")
                output = self.tools.call(name, *args, _confirmed=True, **kwargs)
                logger.info(f"Tool {name} executed successfully")
            except (ValueError, RuntimeError) as exc:
                logger.error(f"Tool error in {name}: {exc}")
                return AgentResult(f"Ошибка инструмента «{name}»: {exc}",
                                   self.provider.name, tool_used=name)
            self._remember(text, str(output))
            return AgentResult(str(output), self.provider.name, tool_used=name)

        if text.startswith("/"):
            return self._handle_tool_command(text)

        logger.debug(f"Generating response via {self.provider.name}")
        try:
            reply = self.provider.generate(text)
            logger.info(f"Response generated (length={len(reply)})")
        except Exception as e:
            logger.error(f"Provider error: {e}", exc_info=True)
            raise
        self._remember(text, reply)
        return AgentResult(reply, self.provider.name)

    def _handle_tool_command(self, text: str) -> AgentResult:
        parts = text[1:].split()
        name, args = parts[0], tuple(parts[1:])
        logger.info(f"Tool command: {name} {' '.join(args)}")
        
        try:
            output = self.tools.call(name, *args)
        except ConfirmationRequired:
            logger.info(f"Tool {name} requires confirmation")
            self._pending_tool = (name, args, {})
            return AgentResult(
                f"Инструмент «{name}» требует подтверждения. Выполнить? (yes/да)",
                self.provider.name, tool_used=name, needs_confirmation=True,
            )
        except KeyError:
            logger.warning(f"Unknown tool: {name}")
            return AgentResult(
                f"Неизвестный инструмент «{name}». Доступны: {', '.join(self.tools.names()) or '—'}",
                self.provider.name,
            )
        except (ValueError, RuntimeError) as exc:
            logger.error(f"Tool error in {name}: {exc}")
            return AgentResult(f"Ошибка инструмента «{name}»: {exc}",
                               self.provider.name, tool_used=name)
        
        logger.info(f"Tool {name} executed successfully")
        self._remember(text, str(output))
        return AgentResult(str(output), self.provider.name, tool_used=name)

    def _remember(self, user: str, assistant: str):
        if self.memory is None:
            return
        try:
            data = self.memory.load()
            history = data.setdefault("history", [])
            history.append({"user": user, "assistant": assistant})
            self.memory.save(data)
            logger.debug("Message saved to memory")
        except Exception as e:
            logger.error(f"Failed to save to memory: {e}", exc_info=True)
