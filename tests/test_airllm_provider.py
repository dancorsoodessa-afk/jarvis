import sys
import types

import pytest

from agent.config import Settings, SUPPORTED_PROVIDERS, normalize_provider
from agent.providers.airllm import AirLLMProvider


def test_airllm_is_supported_and_optional():
    assert "airllm" in SUPPORTED_PROVIDERS
    assert normalize_provider("AirLLM") == "airllm"
    settings = Settings(provider="airllm", airllm_model="test/model")
    assert settings.provider == "airllm"
    assert settings.use_local is True


def test_airllm_does_not_import_or_load_until_generate():
    provider = AirLLMProvider("test/model")
    assert provider._model is None
    assert provider._tokenizer is None


def test_airllm_missing_package_has_clear_error(monkeypatch):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "airllm":
            raise ImportError("blocked in test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    with pytest.raises(RuntimeError, match="AirLLM не установлен"):
        AirLLMProvider("test/model")._load()


def test_airllm_generation_uses_model_and_keeps_history(monkeypatch):
    class FakeTensor:
        shape = (1, 3)
        def cuda(self):
            return self
        def __getitem__(self, item):
            return self

    class FakeTokenizer:
        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            assert add_generation_prompt is True
            return "prompt"
        def __call__(self, *args, **kwargs):
            return {"input_ids": FakeTensor()}
        def decode(self, *args, **kwargs):
            return " Проверенный ответ "

    class FakeModel:
        tokenizer = FakeTokenizer()
        def generate(self, input_ids, **kwargs):
            assert kwargs["max_new_tokens"] == 5
            return types.SimpleNamespace(sequences=[FakeTensor()])

    fake_module = types.SimpleNamespace(AutoModel=types.SimpleNamespace(from_pretrained=lambda name: FakeModel()))
    monkeypatch.setitem(sys.modules, "airllm", fake_module)

    provider = AirLLMProvider("test/model", max_new_tokens=5)
    assert provider.generate("Привет") == "Проверенный ответ"
    assert provider.history[-2:] == [
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Проверенный ответ"},
    ]
