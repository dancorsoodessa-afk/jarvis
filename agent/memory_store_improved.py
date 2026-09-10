from pathlib import Path
import json


class MemoryStore:
    def __init__(self, path="jarvis_memory.json"):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # Лучше бы логировать, но пока молча игнорируем, чтобы не падать