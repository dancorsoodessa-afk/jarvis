"""Runtime tool registry with optional per-tool switches."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ..permissions import audit, severity


class ConfirmationRequired(Exception):
    """Raised when a tool must be confirmed before running."""


@dataclass(frozen=True)
class ToolEntry:
    """A registered tool: its callable plus metadata for specs/confirmation."""

    fn: Callable[..., object]
    confirm: bool = False
    description: str = ""
    parameters: dict[str, str] = field(default_factory=dict)


def _disabled_tools() -> set[str]:
    """Read disabled tools without making the UI or runtime depend on each other."""
    raw = os.environ.get("JARVIS_DISABLED_TOOLS", "")
    if not raw:
        return set()
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return {str(item).strip() for item in value if str(item).strip()}
    except (TypeError, ValueError):
        pass
    return {item.strip() for item in raw.split(",") if item.strip()}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}

    def register(self, name: str, fn: Callable[..., object], confirm: bool = False,
                 description: str | None = None,
                 parameters: dict[str, str] | None = None) -> None:
        """Register a callable unless its switch is currently disabled."""
        if name in _disabled_tools():
            return
        self._tools[name] = ToolEntry(
            fn=fn, confirm=confirm,
            description=description or "", parameters=parameters or {})

    def names(self):
        return tuple(self._tools)

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def spec(self, name: str) -> dict:
        entry = self._tools[name]
        props = {k: {"type": "string", "description": v}
                 for k, v in entry.parameters.items()}
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": entry.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": list(props),
                },
            },
        }

    def specs(self):
        return [self.spec(n) for n, e in self._tools.items() if e.description]

    def call(self, name: str, *args, _confirmed: bool = False,
             **kwargs) -> object:
        entry = self._tools.get(name)
        if entry is None:
            raise KeyError(name)
        if (entry.confirm or severity(name, _confirmed) == "critical") and not _confirmed:
            audit(name, "blocked", "ожидалось подтверждение")
            raise ConfirmationRequired(name)
        if args and len(args) > 1 and len(entry.parameters) == 1 and not kwargs:
            args = (" ".join(map(str, args)),)
        audit(name, "start", severity(name, _confirmed))
        try:
            result = entry.fn(*args, **kwargs)
            audit(name, "success")
            return result
        except Exception as exc:
            audit(name, "error", type(exc).__name__)
            raise
        except TypeError:
            if len(args) > 1 and not kwargs:
                return entry.fn(" ".join(map(str, args)))
            raise
