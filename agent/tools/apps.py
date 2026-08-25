"""Application launching. Always registered with confirm=True."""

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
