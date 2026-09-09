class ConfirmationRequired(Exception):
    """Raised when a tool must be confirmed before running."""


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name, fn, confirm=False, description=None,
                 parameters=None):
        """parameters: JSON-schema-ish dict {"param": "description"}.
        Built into an OpenAI tool spec for function calling."""
        self._tools[name] = (fn, confirm, description or "", parameters or {})

    def names(self):
        return tuple(self._tools)

    def spec(self, name):
        fn, confirm, description, parameters = self._tools[name]
        props = {k: {"type": "string", "description": v}
                 for k, v in parameters.items()}
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": list(props),
                },
            },
        }

    def specs(self):
        return [self.spec(n) for n in self._tools if self._tools[n][2]]

    def call(self, name, *args, _confirmed=False, **kwargs):
        entry = self._tools.get(name)
        if entry is None:
            raise KeyError(name)
        fn, confirm = entry[0], entry[1]
        if confirm and not _confirmed:
            raise ConfirmationRequired(name)
        return fn(*args, **kwargs)
