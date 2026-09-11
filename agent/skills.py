"""Knowledge skills: persistent notes, safe calculator, date/time.

All stdlib, cross-platform. Notes live in the memory JSON store under
"notes": [{"id", "text", "tags", "created"}].
"""

import ast
import datetime as _dt
import json
import operator
import re

MAX_NOTES = 500


# -- Notes (long-term knowledge) --------------------------------------------

class NoteStore:
    """Tiny persistent knowledge base with keyword search."""

    def __init__(self, path):
        from pathlib import Path
        self.path = Path(path)

    def _load(self) -> list:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("notes", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, OSError):
            return []

    def all(self) -> list:
        return self._load()

    def _save(self, notes: list):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if self.path.exists():
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    existing = {}
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing["notes"] = notes[-MAX_NOTES:]
        self.path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def add(self, text: str, tags: str = "") -> str:
        text = " ".join(text.split()).strip()
        if not text:
            raise ValueError("Пустая заметка")
        notes = self._load()
        next_id = max((n["id"] for n in notes), default=0) + 1
        notes.append({
            "id": next_id,
            "text": text[:2000],
            "tags": " ".join(tags.split())[:200],
            "created": _dt.datetime.now().isoformat(timespec="seconds"),
        })
        self._save(notes)
        return f"Запомнил: {text[:100]}"

    def recall(self, query: str = "") -> str:
        notes = self._load()
        if not notes:
            return "Заметок пока нет."
        if query:
            words = query.lower().split()
            notes = [n for n in notes
                     if any(w in (n["text"] + " " + n["tags"]).lower()
                            for w in words)]
            if not notes:
                return "Ничего не нашлось по запросу."
        shown = notes[-10:]
        lines = [f"#{n['id']} [{n['tags']}] {n['text']}" if n["tags"]
                 else f"#{n['id']} {n['text']}" for n in shown]
        if len(notes) > len(shown):
            lines.append(f"...и ещё {len(notes) - len(shown)}")
        return "\n".join(lines)

    def forget(self, note_id) -> str:
        notes = self._load()
        try:
            note_id = int(note_id)
        except (TypeError, ValueError):
            raise ValueError("Укажите номер заметки, например: /forget 3")
        remaining = [n for n in notes if n["id"] != note_id]
        if len(remaining) == len(notes):
            return f"Заметка #{note_id} не найдена."
        self._save(remaining)
        return f"Забыл заметку #{note_id}."


# -- Calculator (safe, no eval) ----------------------------------------------

_CALC_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _calc_node(node):
    if isinstance(node, ast.Expression):
        return _calc_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _CALC_OPS:
        return _CALC_OPS[type(node.op)](_calc_node(node.left),
                                        _calc_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _CALC_OPS:
        return _CALC_OPS[type(node.op)](_calc_node(node.operand))
    raise ValueError("Разрешены только числа и + - * / // % ** ( )")


def calculate(expression: str) -> str:
    """Evaluate arithmetic safely via ast (no eval)."""
    expr = expression.strip().replace(",", ".")
    expr = re.sub(r"[хx×*](?=\s*\d)", "*", expr)  # "2 x 3" / "2 х 3"
    if not expr:
        raise ValueError("Пустое выражение")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Не удалось разобрать выражение: {expression!r}") from exc
    result = _calc_node(tree)
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"{expression.strip()} = {result}"


# -- Date / time --------------------------------------------------------------

def now() -> str:
    d = _dt.datetime.now()
    days = ["понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье"]
    months = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return (f"Сейчас {d.strftime('%H:%M:%S')}, "
            f"{d.day} {months[d.month]} {d.year} года, {days[d.weekday()]}.")
