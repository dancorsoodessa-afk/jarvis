from agent.config import DEFAULT_CHAT_URL, DEFAULT_MODEL, normalize_chat_url, normalize_provider, Settings


def test_default_endpoint_is_gemini():
    assert DEFAULT_CHAT_URL == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert DEFAULT_MODEL == "gemini-2.5-flash"
    assert normalize_chat_url("") == DEFAULT_CHAT_URL
    assert normalize_chat_url(None) == DEFAULT_CHAT_URL


def test_all_configured_endpoints_are_forced_to_gemini():
    assert normalize_chat_url("https://router.huggingface.co/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("http://localhost:11434/v1/chat/completions") == DEFAULT_CHAT_URL


def test_only_gemini_provider_is_allowed():
    assert normalize_provider(None) == "gemini"
    assert normalize_provider("gemini") == "gemini"
    assert normalize_provider("huggingface") == "gemini"


def test_settings_load_gemini_key_without_huggingface_token(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    settings = Settings.from_env()
    assert settings.provider == "gemini"
    assert settings.chat_key == "gemini-test-key"



def test_project_env_loader_respects_existing_process_values(tmp_path, monkeypatch):
    from agent.config import load_project_env

    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_MODEL=gemini-flash-latest\nTTS_LANGUAGE=ru-RU\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.delenv("TTS_LANGUAGE", raising=False)
    load_project_env(env_file)
    assert __import__("os").environ["GEMINI_MODEL"] == "gemini-2.5-flash"
    assert __import__("os").environ["TTS_LANGUAGE"] == "ru-RU"
