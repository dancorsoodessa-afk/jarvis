class ConfirmationRequired(Exception):
    """Raised when a tool must be confirmed before running."""


from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolEntry:
    """A registered tool: its callable plus metadata for specs/confirmation."""

    fn: Callable[..., object]
    confirm: bool = False
    description: str = ""
    parameters: dict[str, str] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}

    def register(self, name: str, fn: Callable[..., object], confirm: bool = False,
                 description: str | None = None,
                 parameters: dict[str, str] | None = None) -> None:
        """Register a callable and its function-calling metadata."""
        self._tools[name] = ToolEntry(
            fn=fn, confirm=confirm,
            description=description or "", parameters=parameters or {})

    def names(self):
        return tuple(self._tools)

    def get(self, name: str) -> ToolEntry | None:
        """Return registered tool metadata without exposing internal storage."""
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
        if entry.confirm and not _confirmed:
            raise ConfirmationRequired(name)
        if args and len(args) > 1 and len(entry.parameters) == 1 \
                and not kwargs:
            args = (" ".join(map(str, args)),)
        try:
            return entry.fn(*args, **kwargs)
        except TypeError:
            if len(args) > 1 and not kwargs:
                return entry.fn(" ".join(map(str, args)))
            raise
