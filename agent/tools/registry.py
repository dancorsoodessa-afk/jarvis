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
        """parameters: JSON-schema-ish dict {"param": "description"}.
        Built into an OpenAI tool spec for function calling."""
        self._tools[name] = ToolEntry(
            fn=fn, confirm=confirm,
            description=description or "", parameters=parameters or {})

    def names(self):
        return tuple(self._tools)

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
        return entry.fn(*args, **kwargs)
