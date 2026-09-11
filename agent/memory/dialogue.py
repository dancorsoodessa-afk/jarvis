"""Short-term (session) + long-term (RAG) dialogue memory.

SessionMemory persists chat_history across restarts and trims it to a
bounded window (project performance rule: bounded, never unbounded).
"""

import datetime as _dt

MAX_EXCHANGES = 40  # user+assistant pairs kept in persistent history


class SessionMemory:
    """Keeps ``chat_history`` (list of role dicts) in the shared memory JSON."""

    def __init__(self, store, max_exchanges: int = MAX_EXCHANGES):
        self.store = store
        self.max_exchanges = max_exchanges

    def load_history(self) -> list[dict]:
        data = self.store.load()
        history = data.get("chat_history", [])
        return [m for m in history
                if isinstance(m, dict) and m.get("role") in ("user", "assistant")]

    def save_history(self, history: list[dict]):
        """Persist history, trimmed to the last max_exchanges*2 messages."""
        keep = self.max_exchanges * 2
        trimmed = history[-keep:] if len(history) > keep else history
        data = self.store.load()
        data["chat_history"] = trimmed
        self.store.save(data)

    def append(self, user: str, assistant: str):
        history = self.load_history()
        history.append({"role": "user", "content": user})
        history.append({"role": "assistant", "content": assistant})
        self.save_history(history)

    def clear(self) -> str:
        self.save_history([])
        return "История диалога очищена."

    def last_user_text(self, n: int = 2) -> list[str]:
        """Recent user messages, for keyword extraction (RAG)."""
        msgs = [m["content"] for m in self.load_history()
                if m.get("role") == "user"]
        return msgs[-n:]


# -- RAG: pick relevant long-term facts into the model's context -------------

_STOP_WORDS = {
    "что", "как", "где", "кто", "когда", "почему", "зачем", "какой",
    "скажи", "привет", "спасибо", "мне", "меня", "тебе", "тебя", "это",
    "the", "and", "you", "what", "how", "who", "when", "why", "please",
}


def keywords(text: str, min_len: int = 4, limit: int = 6) -> list[str]:
    """Low-noise keywords from a phrase (for recall search)."""
    words = []
    for w in text.lower().split():
        w = w.strip(".,!?;:()\"'«»")
        if len(w) >= min_len and w not in _STOP_WORDS:
            words.append(w)
        if len(words) >= limit:
            break
    return words


def relevant_notes(notes, recent_messages: list[str], limit: int = 5) -> str:
    """Return a formatted block of notes relevant to recent messages, or ''."""
    query_words = []
    for msg in recent_messages:
        query_words.extend(keywords(msg))
    if not query_words:
        return ""
    all_notes = notes.all()
    if not all_notes:
        return ""
    scored = []
    for note in all_notes:
        hay = (note["text"] + " " + note["tags"]).lower()
        score = sum(1 for w in query_words if w in hay)
        if score:
            scored.append((score, note))
    scored.sort(key=lambda x: (-x[0], -x[1]["id"]))
    picked = [n for _s, n in scored[:limit]]
    if not picked:
        return ""
    lines = [f"- #{n['id']} {n['text']}" for n in picked]
    return ("Известные факты о пользователе (долговременная память):\n"
            + "\n".join(lines))
