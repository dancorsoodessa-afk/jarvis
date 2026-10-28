import unittest
from unittest import mock

from agent.config import DEFAULT_CHAT_URL, Settings, normalize_chat_url, normalize_provider
from agent.providers.openai_chat import OpenAIChatProvider


class TestCloudOnlyConfiguration(unittest.TestCase):
    def test_provider_is_always_gemini(self):
        for value in (None, "", "gemini", "openai", "openrouter", "local-vulkan", "ollama"):
            self.assertEqual(normalize_provider(value), "gemini")

    def test_endpoint_is_always_gemini(self):
        self.assertEqual(normalize_chat_url(""), DEFAULT_CHAT_URL)
        self.assertEqual(normalize_chat_url("http://localhost:11434/v1/chat/completions"), DEFAULT_CHAT_URL)
        self.assertEqual(normalize_chat_url("https://openrouter.ai/api/v1/chat/completions"), DEFAULT_CHAT_URL)

    def test_settings_do_not_expose_local_model_fields(self):
        settings = Settings.from_env()
        self.assertEqual(settings.provider, "gemini")
        self.assertEqual(settings.chat_url, DEFAULT_CHAT_URL)
        self.assertFalse(hasattr(settings, "llama_cli"))
        self.assertFalse(hasattr(settings, "use_local"))

    def test_provider_rejects_unsupported_or_insecure_endpoint(self):
        for url in (
            "http://api.groq.com/openai/v1/chat/completions",
            "https://openrouter.ai/api/v1/chat/completions",
        ):
            provider = OpenAIChatProvider(url=url, api_key="test", model="test")
            with self.assertRaisesRegex(RuntimeError, "Разрешён только официальный endpoint Gemini"):
                provider._ensure_endpoint()

    def test_provider_defaults_to_gemini_endpoint(self):
        provider = OpenAIChatProvider(url="", api_key="test", model="test")
        provider._ensure_endpoint()
        self.assertEqual(provider.url, DEFAULT_CHAT_URL)


if __name__ == "__main__":
    unittest.main()
