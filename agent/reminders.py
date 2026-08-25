"""Reminders persisted to JSON, fired while the agent is running."""

import json
import time
import uuid
from pathlib import Path


class ReminderService:
    def __init__(self, path: str = "jarvis_reminders.json"):
        self.path = Path(path)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, items: list[dict]):
        self.path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, minutes: str, *text_parts: str) -> str:
        """CLI form: /remind <minutes> <text...>"""
        text = " ".join(text_parts).strip()
        if not text:
            raise ValueError("Reminder text is empty")
        delay = float(minutes)
        if delay <= 0:
            raise ValueError("Minutes must be positive")
        items = self._load()
        due = time.time() + delay * 60
        items.append({"id": uuid.uuid4().hex[:8], "text": text, "due": due})
        self._save(items)
        return f"Напомню через {delay:g} мин: {text}"

    def list_pending(self) -> str:
        items = self._load()
        if not items:
            return "Напоминаний нет"
        now = time.time()
        lines = [
            f"{i['id']}: через {max(0, (i['due'] - now)) / 60:.1f} мин — {i['text']}"
            for i in sorted(items, key=lambda i: i["due"])
        ]
        return "\n".join(lines)

    def pop_due(self) -> list[str]:
        """Return and remove reminders whose time has come."""
        items = self._load()
        now = time.time()
        due, pending = [i for i in items if i["due"] <= now], [i for i in items if i["due"] > now]
        if due:
            self._save(pending)
        return [i["text"] for i in due]
