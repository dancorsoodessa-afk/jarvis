from agent.config import DEFAULT_CHAT_URL, normalize_chat_url, normalize_provider


def test_default_endpoint_is_hugging_face():
    assert DEFAULT_CHAT_URL == "https://router.huggingface.co/v1/chat/completions"
    assert normalize_chat_url("") == DEFAULT_CHAT_URL
    assert normalize_chat_url(None) == DEFAULT_CHAT_URL


def test_all_configured_endpoints_are_forced_to_hugging_face():
    assert normalize_chat_url("https://openrouter.ai/api/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("http://localhost:11434/v1/chat/completions") == DEFAULT_CHAT_URL
    assert normalize_chat_url("https://api.other-provider.example/v1/chat/completions") == DEFAULT_CHAT_URL


def test_only_hugging_face_provider_is_allowed():
    assert normalize_provider(None) == "huggingface"
    assert normalize_provider("huggingface") == "huggingface"
    assert normalize_provider("openai-compatible") == "huggingface"
    assert normalize_provider("local-vulkan") == "huggingface"
