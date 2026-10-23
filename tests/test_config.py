from agent.config import DEFAULT_CHAT_URL, DEFAULT_MODEL, normalize_chat_url, normalize_provider, Settings


def test_default_endpoint_is_groq():
    assert DEFAULT_CHAT_URL == "https://api.groq.com/openai/v1/chat/completions"
    assert DEFAULT_MODEL == "openai/gpt-oss-20b"
    assert normalize_chat_url("") == DEFAULT_CHAT_URL
    assert normalize_chat_url(None) == DEFAULT_CHAT_URL


def test_all_configured_endpoints_are_forced_to_groq():
    assert normalize_chat_url("https://router.huggingface.co/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("https://openrouter.ai/api/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("http://localhost:11434/v1/chat/completions") == DEFAULT_CHAT_URL


def test_only_groq_provider_is_allowed():
    assert normalize_provider(None) == "groq"
    assert normalize_provider("groq") == "groq"
    assert normalize_provider("huggingface") == "groq"
    assert normalize_provider("openai-compatible") == "groq"


def test_settings_load_groq_key_without_huggingface_token(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    settings = Settings.from_env()
    assert settings.provider == "groq"
    assert settings.chat_key == "groq-test-key"
