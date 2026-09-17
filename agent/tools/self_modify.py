"""Self-modification tools for the local Буся agent.

The agent may inspect and edit source files inside its own repository, create a
backup, run the project's tests, and restore the last backup. This is intended
for the Windows/local runtime; an installed Android APK cannot rewrite its own
signed source files.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKUP_ROOT = ROOT / ".jarvis_backups"
ALLOWED_SUFFIXES = {
    ".py", ".dart", ".kt", ".java", ".xml", ".yaml", ".yml", ".json",
    ".md", ".toml", ".ps1", ".txt", ".html", ".css", ".js", ".ts",
}


def _safe_path(path: str) -> Path:
    candidate = (ROOT / path).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("Путь выходит за пределы проекта Буся") from exc
    if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"Редактирование расширения {candidate.suffix or '<none>'} запрещено")
    return candidate


def read_source(path: str) -> str:
    """Read a source/config file from the project."""
    target = _safe_path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    return target.read_text(encoding="utf-8")


def write_source(path: str, content: str) -> str:
    """Backup and replace a project source/config file."""
    target = _safe_path(path)
    if len(content) > 2_000_000:
        raise ValueError("Файл слишком большой для одной операции")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = BACKUP_ROOT / f"{stamp}_{target.relative_to(ROOT).as_posix().replace('/', '__')}"
    if target.exists():
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Изменено: {target.relative_to(ROOT)}; резервная копия: {backup.relative_to(ROOT)}"


def run_tests() -> str:
    """Run the project's Python tests after a self-change."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return f"Код возврата: {proc.returncode}\n{output[-12000:]}"


def git_status() -> str:
    """Show the current repository state."""
    proc = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    return (proc.stdout + "\n" + proc.stderr).strip()


def rollback_last_backup() -> str:
    """Restore the newest backup created by write_source."""
    backups = sorted(BACKUP_ROOT.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        raise FileNotFoundError("Резервных копий нет")
    backup = backups[0]
    marker = backup.name.split("_", 2)[-1]
    relative = marker.replace("__", "/")
    target = _safe_path(relative)
    target.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    return f"Восстановлено: {target.relative_to(ROOT)} из {backup.relative_to(ROOT)}"
