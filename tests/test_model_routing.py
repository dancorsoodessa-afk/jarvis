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

def test_router_uses_groq_when_all_gemini_roles_share_a_failed_backend():
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

    gemini_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    providers = {
        "fast": EndpointProvider("gemini-fast", gemini_url, "gemini-key", "Ошибка API: HTTP 503. overloaded"),
        "reasoning": EndpointProvider("gemini-reasoning", gemini_url, "gemini-key"),
        "coding": EndpointProvider("gemini-coding", gemini_url, "gemini-key"),
        "additional": EndpointProvider("gemini-additional", gemini_url, "gemini-key"),
        "groq": EndpointProvider("groq", "https://api.groq.com/openai/v1/chat/completions", "groq-key"),
    }
    router = RoleRouterProvider(providers)
    assert router.generate("обычный вопрос") == "ok:groq"
    assert providers["fast"].calls == 1
    assert providers["reasoning"].calls == 0
    assert providers["groq"].calls == 1


def test_router_propagates_stream_callback_to_selected_provider():
    callback = lambda _delta: None
    providers = {r: FakeProvider(r) for r in ("fast", "reasoning", "coding", "additional")}
    router = RoleRouterProvider(providers)
    router.on_delta = callback
    router.generate("Открой браузер")
    assert providers["fast"].on_delta is callback
