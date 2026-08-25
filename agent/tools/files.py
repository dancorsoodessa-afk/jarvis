"""File tools. Search is read-only; delete requires confirmation."""

import fnmatch
import os
from pathlib import Path

MAX_RESULTS = 50


def search(pattern: str, root: str = ".") -> list[str]:
    """Find files matching a glob pattern under root, capped at MAX_RESULTS."""
    root_path = Path(root).expanduser()
    if not root_path.is_dir():
        raise ValueError(f"Not a directory: {root}")
    matches = []
    for dirpath, _dirnames, filenames in os.walk(root_path):
        for name in filenames:
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                matches.append(str(Path(dirpath) / name))
                if len(matches) >= MAX_RESULTS:
                    return matches
    return matches


def delete(path: str) -> str:
    """Delete a single file. Must be registered with confirm=True."""
    target = Path(path).expanduser()
    if not target.is_file():
        raise ValueError(f"Not a file: {path}")
    target.unlink()
    return f"Deleted: {target}"
