class ConfirmationRequired(Exception):
    """Raised when a tool must be confirmed before running."""


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name, fn, confirm=False):
        self._tools[name] = (fn, confirm)

    def names(self):
        return tuple(self._tools)

    def call(self, name, *args, _confirmed=False, **kwargs):
        fn, confirm = self._tools[name]
        if confirm and not _confirmed:
            raise ConfirmationRequired(name)
        return fn(*args, **kwargs)
