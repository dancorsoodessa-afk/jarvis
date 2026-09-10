"""Application launching and safe URL/path opening."""

import shlex
import subprocess
import sys
from pathlib import Path


def launch(command: str) -> str:
    """Start a program without blocking the agent. Requires confirmation."""
    command = command.strip()
    if not command:
        raise ValueError("Empty command")
    if sys.platform == "win32":
        import os
        os.startfile(command)  # noqa: S606
    else:
        subprocess.Popen(shlex.split(command))  # noqa: S603
    return f"Started: {command}"


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
