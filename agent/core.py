from dataclasses import dataclass
from typing import Protocol

from .tools.registry import ConfirmationRequired, ToolRegistry
from .memory.store import MemoryStore
from .logging_setup import get as get_log


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
        self.on_exchange = None
        self.context_hook = None
        self.log = get_log("core")

    def _notify(self, user: str, assistant: str):
        self._remember(user, assistant)
        if self.on_exchange:
            try:
                self.on_exchange(user, assistant)
            except Exception:
                self.log.warning("on_exchange callback failed", exc_info=True)

    def handle(self, message: str, attachment: dict | None = None) -> AgentResult:
        text = message.strip()
        if not text:
            return AgentResult("Я здесь. Что нужно сделать?", self.provider.name)
        due = self._due_reminders()
        result = self._dispatch(text, attachment=attachment)
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

    def _dispatch(self, text: str, attachment: dict | None = None) -> AgentResult:
        if self._pending_tool:
            if text.lower() not in ("yes", "y", "да", "д"):
                self._pending_tool = None
                return AgentResult("Отменено.", self.provider.name)
            name, args, kwargs = self._pending_tool
            self._pending_tool = None
            return self._run_tool(name, remember=text,
                                  confirmed=True, *args, **kwargs)

        if text.startswith("/"):
            return self._handle_tool_command(text)

        # Deterministic local intents must not depend on Gemini function calling.
        # Keep this deliberately narrow: read-only status/search and explicit volume
        # changes only; risky actions still require the normal confirmation gate.
        local_result = self._dispatch_local_intent(text)
        if local_result is not None:
            self._notify(text, local_result.text)
            return local_result

        if self.context_hook:
            try:
                self.context_hook(text)
            except Exception:
                self.log.warning("context_hook failed", exc_info=True)
        generate = self.provider.generate
        try:
            if hasattr(self.provider, "tool_executor"):
                self.provider.tool_executor = self._execute_for_llm
                prompt = {"text": text, "attachment": attachment} if attachment else text
                reply = generate(prompt, tools=self.tools.specs())
            else:
                prompt = {"text": text, "attachment": attachment} if attachment else text
                reply = generate(prompt)
        except (ValueError, RuntimeError, OSError) as exc:
            self.log.warning("Ошибка провайдера: %s", exc)
            return AgentResult(f"Ошибка провайдера: {exc}", self.provider.name)
        self.log.info("Ответ модели (%s): %.120s", self.provider.name, reply)
        self._notify(text, reply)
        return AgentResult(reply, self.provider.name,
                           needs_confirmation=self._pending_tool is not None)

    def _dispatch_local_intent(self, text: str) -> AgentResult | None:
        import re
        value = " ".join(text.lower().replace("ё", "е").split())
        # Exact local system status phrases.
        if value in {"статус системы", "состояние системы", "проверь систему", "покажи состояние компьютера"}:
            return self._run_tool("status")
        if value in {"громкость", "проверь громкость", "какая громкость", "покажи громкость"}:
            return self._run_tool("volume")
        match = re.fullmatch(r"(?:установи|поставь|сделай) громкость(?: на)?\s+(\d{1,3})%?", value)
        if match:
            level = int(match.group(1))
            if not 0 <= level <= 100:
                return AgentResult("Громкость должна быть от 0 до 100 процентов.", self.provider.name)
            return self._run_tool("set_volume", str(level))
        if value in {"дата и время", "который час", "сколько времени", "текущее время"}:
            for name in ("now", "time"):
                if self.tools.get(name):
                    return self._run_tool(name)
        # File search is local and read-only. Never infer destructive file actions.
        if value.startswith("найди файл "):
            pattern = text.strip()[len("найди файл "):].strip().strip('"')
            if pattern and self.tools.get("search"):
                try:
                    output = self.tools.call("search", pattern, root=".")
                except Exception as exc:
                    return AgentResult(f"Локальный поиск файлов завершился ошибкой: {exc}", self.provider.name)
                found = list(output or [])
                summary = "\n".join(str(item) for item in found[:20]) if found else "Совпадений не найдено."
                return AgentResult(summary, self.provider.name, tool_used="search")
        return None

    def _run_tool(self, name: str, *args, remember: str | None = None,
                  confirmed: bool = False, ask_confirmation: bool = True,
                  **kwargs) -> AgentResult:
        try:
            output = self.tools.call(name, *args, _confirmed=confirmed, **kwargs)
        except ConfirmationRequired:
            if ask_confirmation:
                self._pending_tool = (name, args, kwargs)
                return AgentResult(
                    f"Инструмент «{name}» требует подтверждения. Выполнить? (yes/да)",
                    self.provider.name, tool_used=name, needs_confirmation=True,
                )
            return AgentResult(
                "Инструмент требует подтверждения пользователя. "
                "Автоматически опасное действие не выполняю.",
                self.provider.name, tool_used=name,
            )
        except KeyError:
            return AgentResult(
                f"Неизвестный инструмент «{name}». "
                f"Доступны: {', '.join(self.tools.names()) or '—'}",
                self.provider.name,
            )
        except (TypeError, ValueError, RuntimeError, OSError) as exc:
            return AgentResult(f"Ошибка инструмента «{name}»: {exc}",
                               self.provider.name, tool_used=name)
        if remember is not None:
            self._remember(remember, str(output))
        return AgentResult(str(output), self.provider.name, tool_used=name)

    def _execute_for_llm(self, name: str, args: dict) -> str:
        """Execute a model-requested tool through the same safety gate as CLI tools."""
        entry = self.tools.get(name)
        if entry is None:
            raise KeyError(name)
        if not isinstance(args, dict):
            raise TypeError("Аргументы инструмента должны быть объектом JSON")
        self.log.info("Модель вызвала инструмент %s", name)
        return self._run_tool(name, ask_confirmation=True, **args).text

    def _handle_tool_command(self, text: str) -> AgentResult:
        import shlex
        try:
            parts = shlex.split(text[1:])
        except ValueError:
            parts = text[1:].split()
        if not parts:
            return AgentResult(
                "Не указана команда. Доступные инструменты: "
                f"{', '.join(self.tools.names()) or '—'}",
                self.provider.name,
            )
        name, args = parts[0], tuple(parts[1:])
        if name.lower() == "tools":
            names = self.tools.names()
            output = "Доступные инструменты: " + (", ".join(names) if names else "—")
            self._remember(text, output)
            return AgentResult(output, self.provider.name)
        return self._run_tool(name, *args, remember=text)

    def _remember(self, user: str, assistant: str):
        if self.memory is None:
            return
        data = self.memory.load()
        history = data.setdefault("history", [])
        history.append({"user": user, "assistant": assistant})
        data["history"] = history[-40:]
        self.memory.save(data)
