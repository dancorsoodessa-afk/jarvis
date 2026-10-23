from agent.config import DEFAULT_CHAT_URL, normalize_chat_url, normalize_provider


def test_default_endpoint_is_google_gemini():
    assert DEFAULT_CHAT_URL == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert normalize_chat_url("") == DEFAULT_CHAT_URL
    assert normalize_chat_url(None) == DEFAULT_CHAT_URL


def test_all_configured_endpoints_are_forced_to_gemini():
    assert normalize_chat_url("https://router.huggingface.co/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("http://localhost:11434/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("https://api.other-provider.example/v1/chat/completions") == DEFAULT_CHAT_URL


def test_only_gemini_provider_is_allowed():
    assert normalize_provider(None) == "gemini"
    assert normalize_provider("gemini") == "gemini"
    assert normalize_provider("huggingface") == "gemini"
    assert normalize_provider("openai-compatible") == "gemini"
