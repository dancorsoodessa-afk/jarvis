from agent.core_router import classify_role, RoleRouterProvider

class FakeProvider:
    def __init__(self, name):
        self.name = name
        self.calls = 0
        self.last_used_model = name
        self.tool_executor = None
    def generate(self, prompt, tools=None, max_steps=4):
        self.calls += 1
        return f"ok:{self.name}"

def test_role_classification():
    assert classify_role("Открой браузер").role == "fast"
    assert classify_role("Глубоко проанализируй архитектуру проекта").role == "reasoning"
    assert classify_role("Исправь Python код и собери EXE").role == "coding"
    assert classify_role("Дай второе мнение и перепроверь").role == "additional"

def test_router_uses_selected_role():
    providers = {r: FakeProvider(r) for r in ("fast", "reasoning", "coding", "additional")}
    router = RoleRouterProvider(providers)
    assert router.generate("Исправь код") == "ok:coding"
    assert router.last_role == "coding"
    assert providers["coding"].calls == 1
    assert providers["fast"].calls == 0

def test_router_falls_back_after_failure():
    class Broken(FakeProvider):
        def generate(self, prompt, tools=None, max_steps=4):
            self.calls += 1
            raise RuntimeError("down")
    providers = {r: FakeProvider(r) for r in ("fast", "reasoning", "coding", "additional")}
    providers["reasoning"] = Broken("reasoning")
    router = RoleRouterProvider(providers)
    assert router.generate("Проанализируй ошибку") == "ok:fast"


def test_router_skips_same_backend_after_connection_failure():
    class EndpointProvider(FakeProvider):
        def __init__(self, name, url, api_key, error=None):
            super().__init__(name)
            self.url = url
            self.api_key = api_key
            self.error = error
        def generate(self, prompt, tools=None, max_steps=4):
            self.calls += 1
            if self.error:
                raise RuntimeError(self.error)
            return f"ok:{self.name}"

    shared_url = "https://openrouter.ai/api/v1/chat/completions"
    providers = {
        "fast": EndpointProvider("fast", shared_url, "same-key", "Не удалось подключиться к ИИ: DNS"),
        "reasoning": EndpointProvider("reasoning", shared_url, "same-key"),
        "coding": EndpointProvider("coding", "https://independent.example/v1/chat/completions", "other-key"),
        "additional": EndpointProvider("additional", shared_url, "same-key"),
    }
    router = RoleRouterProvider(providers)
    assert router.generate("обычный вопрос") == "ok:coding"
    assert providers["fast"].calls == 1
    assert providers["reasoning"].calls == 0
    assert providers["coding"].calls == 1
    assert providers["additional"].calls == 0


def test_router_skips_same_backend_after_auth_failure():
    class Unauthorized(FakeProvider):
        def __init__(self, name, url, api_key):
            super().__init__(name)
            self.url = url
            self.api_key = api_key
        def generate(self, prompt, tools=None, max_steps=4):
            self.calls += 1
            raise RuntimeError("Ошибка API: HTTP 401. invalid key")

    shared_url = "https://openrouter.ai/api/v1/chat/completions"
    providers = {
        "fast": Unauthorized("fast", shared_url, "same-key"),
        "reasoning": Unauthorized("reasoning", shared_url, "same-key"),
        "coding": FakeProvider("coding"),
        "additional": FakeProvider("additional"),
    }
    router = RoleRouterProvider(providers)
    assert router.generate("обычный вопрос") == "ok:coding"
    assert providers["fast"].calls == 1
    assert providers["reasoning"].calls == 0

def test_router_fallback_order_contains_only_gemini_roles():
    from agent.model_router import RoleRouterProvider
    providers = {name: FakeProvider(name) for name in ("fast", "reasoning", "coding", "additional")}
    router = RoleRouterProvider(providers)
    assert all(name in providers for name in router.fallback_order)
    assert "groq" not in router.fallback_order


def test_router_propagates_stream_callback_to_selected_provider():
    callback = lambda _delta: None
    providers = {r: FakeProvider(r) for r in ("fast", "reasoning", "coding", "additional")}
    router = RoleRouterProvider(providers)
    router.on_delta = callback
    router.generate("Открой браузер")
    assert providers["fast"].on_delta is callback


def test_openai_compatible_provider_fails_over_after_gemini_capacity_error():
    from unittest.mock import patch
    from agent.providers.openai_chat import OpenAIChatProvider

    provider = OpenAIChatProvider(
        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        api_key="test-key",
        model="gemini-3.8-flash",
        fallback_models=["gemini-3.8-flash", "gemini-3.5-flash-lite"],
    )
    successful = {"choices": [{"message": {"content": "резервная модель ответила", "tool_calls": []}}]}
    models_seen = []
    def request(payload):
        models_seen.append(payload["model"])
        if len(models_seen) == 1:
            raise RuntimeError("Gemini временно перегружен (HTTP 503). overloaded")
        return successful
    with patch.object(provider, "discover_model", return_value="gemini-3.8-flash"), \
         patch.object(provider, "_request", side_effect=request) as mocked_request:
        result = provider.generate("проверь резерв")

    assert result == "резервная модель ответила"
    assert mocked_request.call_count == 2
    assert models_seen == ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    assert provider.last_used_model == "gemini-3.5-flash-lite"

def test_router_skips_shared_backend_after_timeout():
    class EndpointProvider(FakeProvider):
        def __init__(self, name, url, api_key, error=None):
            super().__init__(name)
            self.url = url
            self.api_key = api_key
            self.error = error
        def generate(self, prompt, tools=None, max_steps=4):
            self.calls += 1
            if self.error:
                raise RuntimeError(self.error)
            return f"ok:{self.name}"

    shared_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    providers = {
        "fast": EndpointProvider("fast", shared_url, "same-key", "Тайм-аут запроса к Gemini (30 с)"),
        "reasoning": EndpointProvider("reasoning", shared_url, "same-key"),
        "coding": EndpointProvider("coding", "https://api.groq.com/openai/v1/chat/completions", "other-key"),
    }
    router = RoleRouterProvider(providers)
    assert router.generate("обычный вопрос") == "ok:coding"
    assert providers["fast"].calls == 1
    assert providers["reasoning"].calls == 0
    assert providers["coding"].calls == 1


def test_openai_compatible_provider_fails_over_when_model_is_not_found():
    from unittest.mock import patch
    from agent.providers.openai_chat import OpenAIChatProvider

    provider = OpenAIChatProvider(
        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        api_key="test-key",
        model="models/openrouter/free",
        fallback_models=["gemini-3.5-flash-lite"],
    )
    successful = {"choices": [{"message": {"content": "резервная модель ответила", "tool_calls": []}}]}
    models_seen = []
    def request(payload):
        models_seen.append(payload["model"])
        if len(models_seen) == 1:
            raise RuntimeError("Ошибка API: HTTP 404. models/openrouter/free is not found for API version")
        return successful
    with patch.object(provider, "discover_model", return_value="models/openrouter/free"), \
         patch.object(provider, "_request", side_effect=request) as mocked_request:
        result = provider.generate("проверь модель")

    assert result == "резервная модель ответила"
    assert mocked_request.call_count == 2
    assert models_seen == ["models/openrouter/free", "gemini-3.5-flash-lite"]
    assert provider.last_used_model == "gemini-3.5-flash-lite"


def test_openai_compatible_provider_reports_timeout_without_retrying():
    import socket
    import pytest
    from unittest.mock import patch
    from agent.providers.openai_chat import OpenAIChatProvider

    provider = OpenAIChatProvider(
        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        api_key="test-key",
        model="gemini-3.5-flash-lite",
        timeout=5,
    )
    with patch("urllib.request.urlopen", side_effect=socket.timeout("read timed out")) as urlopen:
        with pytest.raises(RuntimeError, match="Тайм-аут запроса"):
            provider._request({"model": "gemini-3.5-flash-lite", "messages": []})
    assert urlopen.call_count == 1


def test_gemini_tool_call_extract_preserves_thought_signature():
    from agent.providers.openai_chat import OpenAIChatProvider

    signature = "opaque-signature-from-gemini"
    provider = OpenAIChatProvider(
        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        api_key="test-key",
        model="gemini-3.5-flash-lite",
    )
    body = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "extra_content": {"google": {"thought_signature": signature}},
                    "function": {"name": "web_search", "arguments": "{\\"query\\":\\"test\\"}"},
                }],
            }
        }]
    }

    extracted = provider._extract(body)
    assert extracted["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == signature
    # The exact assistant tool-call object must be appended to the next request.
    history_message = {"role": "assistant", "content": extracted["content"], "tool_calls": extracted["tool_calls"]}
    assert history_message["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == signature


def test_gemini_stream_tool_call_keeps_extra_content_signature():
    import json
    from unittest.mock import patch
    from agent.providers.openai_chat import OpenAIChatProvider

    signature = "stream-signature"
    chunks = [
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call-1", "type": "function",
            "extra_content": {"google": {"thought_signature": signature}},
            "function": {"name": "web_search", "arguments": "{\\"query\\":\\"x\\"}"},
        }]}}]},
        "[DONE]",
    ]

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def __iter__(self):
            for chunk in chunks:
                if chunk == "[DONE]":
                    yield b"data: [DONE]" + bytes([10])
                else:
                    yield ("data: " + json.dumps(chunk) + chr(10)).encode("utf-8")

    provider = OpenAIChatProvider(
        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        api_key="test-key",
        model="gemini-3.5-flash-lite",
    )
    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        body = provider._request_stream({"model": provider.model, "messages": []})
    tool_call = body["choices"][0]["message"]["tool_calls"][0]
    assert tool_call["extra_content"]["google"]["thought_signature"] == signature
