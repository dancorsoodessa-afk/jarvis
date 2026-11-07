"""Self-modification tools for the local Буся agent.

The agent may inspect and edit source files inside its own repository, create a
backup, run the project's tests, and restore the last backup. This is intended
for the Windows/local runtime; an installed Android APK cannot rewrite its own
signed source files.
"""
from __future__ import annotations

import json
import re
import shutil
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
    if not target.is_file():
        raise FileNotFoundError(path)
    return target.read_text(encoding="utf-8")


def write_source(path: str, content: str) -> str:
    """Backup and replace a project source/config file."""
    target = _safe_path(path)
    if target.exists() and not target.is_file():
        raise ValueError("Можно изменять только файлы, не папки")
    if len(content) > 2_000_000:
        raise ValueError("Файл слишком большой для одной операции")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = BACKUP_ROOT / stamp
    backup = backup_dir / target.relative_to(ROOT)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        backup_reference = backup
    else:
        backup_reference = backup_dir / "__created__.json"
        backup_reference.write_text(
            json.dumps({"path": target.relative_to(ROOT).as_posix()}, ensure_ascii=False),
            encoding="utf-8",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Изменено: {target.relative_to(ROOT)}; резервная копия: {backup_reference.relative_to(ROOT)}"


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
    if not BACKUP_ROOT.exists():
        raise FileNotFoundError("Резервных копий нет")

    # New backups preserve the original relative path inside a timestamp folder.
    backup_dirs = sorted(
        (path for path in BACKUP_ROOT.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for backup_dir in backup_dirs:
        created_marker = backup_dir / "__created__.json"
        if created_marker.is_file():
            data = json.loads(created_marker.read_text(encoding="utf-8"))
            relative = str(data.get("path") or "")
            target = _safe_path(relative)
            if target.is_file():
                target.unlink()
            return f"Удалён новый файл: {target.relative_to(ROOT)}"

        candidates = sorted(
            (path for path in backup_dir.rglob("*") if path.is_file() and path.name != "__created__.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            continue
        backup = candidates[0]
        relative = backup.relative_to(backup_dir).as_posix()
        target = _safe_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        return f"Восстановлено: {target.relative_to(ROOT)} из {backup.relative_to(ROOT)}"

    # Backward compatibility for backups created by the previous flat naming scheme.
    legacy = sorted(
        (path for path in BACKUP_ROOT.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for backup in legacy:
        match = re.match(r"^\d{8}_\d{6}_\d{6}_(.+)$", backup.name)
        if not match:
            continue
        relative = match.group(1).replace("__", "/")
        target = _safe_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
        return f"Восстановлено: {target.relative_to(ROOT)} из {backup.relative_to(ROOT)}"

    raise FileNotFoundError("Резервных копий нет")
