"""Application launching and safe URL opening."""

import shlex
import subprocess
import sys


def launch(command: str) -> str:
    """Start a program without blocking the agent. Requires confirmation."""
    command = command.strip()
    if not command:
        raise ValueError("Empty command")
    if sys.platform == "win32":
        # os.startfile resolves PATH, .lnk files and file associations.
        import os
        os.startfile(command)  # noqa: S606
    else:
        subprocess.Popen(shlex.split(command))  # noqa: S603
    return f"Started: {command}"


def open_url(url: str) -> str:
    """Open an HTTP(S) URL in the user's default browser.

    Unlike arbitrary application launching, this only accepts web URLs and
    therefore does not execute a local command or program.
    """
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
