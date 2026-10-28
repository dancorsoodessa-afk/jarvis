from agent.core_router import RoleRouterProvider, classify_role


class FakeProvider:
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    api_key = "test-key"
    model = "gemini-test"

    def health_check(self):
        return "ONLINE"


def test_role_router_fallback_only_uses_supported_roles():
    router = RoleRouterProvider({})
    assert router.fallback_order == ("fast", "reasoning", "coding", "additional")


def test_role_router_health_check_reports_only_gemini_when_unconfigured():
    assert RoleRouterProvider({}).health_checks() == {"Gemini API": "NOT CONFIGURED"}


def test_role_router_checks_gemini_backend():
    result = RoleRouterProvider({"fast": FakeProvider()}).health_checks()
    assert result == {"Gemini API": "ONLINE"}


def test_classify_code_task():
    assert classify_role("Исправь ошибку Python").role == "coding"
