"""Persistent user preferences explicitly saved by SUPERMAN.

Only store preferences the user asks to remember or explicitly confirms.
This is a lightweight preference store, not passive surveillance or model training.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

MAX_PREFERENCES = 500
_LOCK = threading.RLock()
_STORE_PATH = Path.home() / ".superman" / "preferences.json"


def _load() -> list[dict[str, str]]:
    if not _STORE_PATH.exists():
        return []
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("key") and item.get("value")]


def _save(items: list[dict[str, str]]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_STORE_PATH.parent, prefix="preferences.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(items[-MAX_PREFERENCES:], handle, ensure_ascii=False, indent=2)
        os.replace(tmp, _STORE_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def remember_preference(key: str, value: str) -> str:
    """Persist an explicit preference using a stable key."""
    key = " ".join(str(key).split()).strip()[:120]
    value = " ".join(str(value).split()).strip()[:1000]
    if not key or not value:
        raise ValueError("Укажите название привычки/предпочтения и его значение")
    with _LOCK:
        items = _load()
        now = datetime.now(timezone.utc).isoformat()
        for item in items:
            if item["key"].casefold() == key.casefold():
                item["value"] = value
                item["updated_at"] = now
                _save(items)
                return f"Запомнил предпочтение «{key}»: {value}"
        items.append({"key": key, "value": value, "created_at": now, "updated_at": now})
        _save(items)
    return f"Запомнил предпочтение «{key}»: {value}"


def list_preferences(query: str = "") -> str:
    """List saved preferences, optionally filtered by key/value."""
    query = " ".join(str(query).split()).strip().casefold()
    with _LOCK:
        items = _load()
    if query:
        items = [item for item in items if query in item["key"].casefold() or query in item["value"].casefold()]
    if not items:
        return "Сохранённых предпочтений не найдено."
    return "\n".join(f"- {item['key']}: {item['value']}" for item in items)


def forget_preference(key: str) -> str:
    """Delete one saved preference by its exact key."""
    key = " ".join(str(key).split()).strip()
    if not key:
        raise ValueError("Укажите название предпочтения для удаления")
    with _LOCK:
        items = _load()
        remaining = [item for item in items if item["key"].casefold() != key.casefold()]
        if len(remaining) == len(items):
            return f"Предпочтение «{key}» не найдено."
        _save(remaining)
    return f"Забыл предпочтение «{key}»."
