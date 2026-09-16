"""Bounded Windows command execution.

No shell is used. Only a small allowlist of diagnostic executables is allowed;
anything else is rejected before subprocess creation.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ALLOWED_READONLY = {
    "whoami.exe", "hostname.exe", "ipconfig.exe", "tasklist.exe",
    "systeminfo.exe", "where.exe", "ping.exe", "tracert.exe",
}
ALLOWED_MUTATING = {"taskkill.exe"}


def _parse(command: str) -> list[str]:
    import shlex
    parts = shlex.split(command, posix=False)
    if not parts:
        raise ValueError("Пустая команда")
    exe = Path(parts[0].strip('"')).name.lower()
    if not exe.endswith(".exe"):
        exe += ".exe"
    if exe not in ALLOWED_READONLY and exe not in ALLOWED_MUTATING:
        raise ValueError(f"Команда запрещена: {exe}. Разрешены только безопасные системные команды.")
    parts[0] = exe
    return parts


def run(command: str, timeout: int = 15) -> str:
    """Run one allowlisted Windows executable without a shell."""
    if os.name != "nt":
        raise RuntimeError("Этот инструмент предназначен для Windows.")
    argv = _parse(command)
    timeout = max(1, min(int(timeout), 60))
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=os.environ.get("USERPROFILE") or None,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Команда превысила тайм-аут {timeout} сек.") from exc
    output = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    output = output[:8000]
    if proc.returncode != 0:
        raise RuntimeError(f"Команда завершилась с кодом {proc.returncode}: {output}")
    return output or "Команда выполнена без вывода."
