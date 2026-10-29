from agent.gemini_web import GEMINI_WEB_URL, handoff_to_gemini_web


def test_gemini_web_handoff_copies_prompt_and_opens_official_app():
    copied = []
    opened = []

    result = handoff_to_gemini_web(
        "  Проверь проект Jarvis  ",
        copied.append,
        lambda url: opened.append(url) or True,
    )

    assert copied == ["Проверь проект Jarvis"]
    assert opened == [GEMINI_WEB_URL]
    assert result == {"opened": True, "prompt_copied": True}


def test_gemini_web_handoff_opens_without_overwriting_clipboard_for_empty_prompt():
    copied = []
    opened = []

    result = handoff_to_gemini_web(
        "   ",
        copied.append,
        lambda url: opened.append(url) or True,
    )

    assert copied == []
    assert opened == [GEMINI_WEB_URL]
    assert result == {"opened": True, "prompt_copied": False}
