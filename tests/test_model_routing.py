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
