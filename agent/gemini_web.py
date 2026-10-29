"""Browser handoff helpers for Google's consumer Gemini web app.

The consumer web app is not a supported chat-completions API. This helper
opens the official UI and copies a prompt for the user to submit manually.
"""
from collections.abc import Callable

GEMINI_WEB_URL = "https://gemini.google.com/app"


def handoff_to_gemini_web(
    prompt: str,
    copy_text: Callable[[str], None],
    open_url: Callable[[str], bool],
) -> dict[str, bool]:
    """Open Gemini Web and optionally copy the current prompt to the clipboard."""
    cleaned = (prompt or "").strip()
    if cleaned:
        copy_text(cleaned)
    opened = bool(open_url(GEMINI_WEB_URL))
    return {"opened": opened, "prompt_copied": bool(cleaned)}
