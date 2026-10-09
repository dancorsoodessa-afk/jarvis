from agent.config import DEFAULT_CHAT_URL, normalize_chat_url


def test_empty_chat_url_uses_default_endpoint():
    assert normalize_chat_url("") == DEFAULT_CHAT_URL
    assert normalize_chat_url(None) == DEFAULT_CHAT_URL


def test_localhost_openai_compatible_endpoint_is_preserved():
    url = "http://127.0.0.1:1234/v1/chat/completions"
    assert normalize_chat_url(url) == url


def test_localhost_ollama_endpoint_is_preserved():
    url = "http://localhost:11434/v1/chat/completions"
    assert normalize_chat_url(url) == url


def test_custom_remote_endpoint_is_preserved():
    url = "https://api.groq.com/openai/v1/chat/completions"
    assert normalize_chat_url(url) == url
