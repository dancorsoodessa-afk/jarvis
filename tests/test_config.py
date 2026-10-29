from agent.config import DEFAULT_CHAT_URL, DEFAULT_MODEL, normalize_chat_url, normalize_provider, Settings


def test_default_model_is_removed_for_gemini_web_only():
    assert DEFAULT_CHAT_URL == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert DEFAULT_MODEL == ""
    assert normalize_chat_url("") == DEFAULT_CHAT_URL
    assert normalize_chat_url(None) == DEFAULT_CHAT_URL


def test_all_configured_endpoints_are_forced_to_gemini():
    assert normalize_chat_url("https://router.huggingface.co/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("https://api.groq.com/openai/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("http://localhost:11434/v1/chat/completions") == DEFAULT_CHAT_URL


def test_only_gemini_provider_is_allowed():
    assert normalize_provider(None) == "gemini"
    assert normalize_provider("gemini") == "gemini"
    assert normalize_provider("huggingface") == "gemini"
    assert normalize_provider("groq") == "gemini"


def test_gemini_web_mode_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    settings = Settings.from_env()
    assert settings.provider == "gemini"
    assert settings.chat_key == ""\n    assert settings.chat_model == ""
