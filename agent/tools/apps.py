"""Application launching and safe URL/path opening."""

import re
import shlex
import subprocess
import sys
from pathlib import Path


_BARE_APP_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def launch_needs_confirmation(*args, **kwargs) -> bool:
    """A bare app name (notepad, calc, chrome) is safe; paths, scripts and
    anything with arguments must be confirmed by the user."""
    target = args[0] if args else (kwargs.get("command") or kwargs.get("name") or "")
    return not _BARE_APP_NAME.match(str(target).strip())


def launch(command: str = "", name: str = "") -> str:
    """Start a program without blocking the agent."""
    command = command or name
    command = command.strip()
    if not command:
        raise ValueError("Empty command")
    if sys.platform == "win32":
        import os
        os.startfile(command)  # noqa: S606
    else:
        subprocess.Popen(shlex.split(command))  # noqa: S603
    return f"Запущено: {command}"


def open_url(url: str) -> str:
    """Open an HTTP(S) URL in the user's default browser."""
    url = url.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("Only http:// and https:// URLs are allowed")
    if sys.platform == "win32":
        import os
        os.startfile(url)  # noqa: S606
    else:
        import webbrowser
        webbrowser.open(url)
    return f"Открываю: {url}"


def open_path(path: str) -> str:
    """Open a local file or directory with the Windows shell."""
    raw = path.strip().strip('"')
    if not raw:
        raise ValueError("Путь не указан")
    if sys.platform == "win32":
        import os
        target = Path(raw).expanduser()
        if not target.exists():
            raise ValueError(f"Путь не найден: {raw}")
        os.startfile(str(target))  # noqa: S606
    else:
        target = Path(raw).expanduser()
        if not target.exists():
            raise ValueError(f"Путь не найден: {raw}")
        import webbrowser
        webbrowser.open(target.as_uri())
    return f"Открываю: {raw}"
