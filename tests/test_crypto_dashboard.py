from pathlib import Path


def test_crypto_dashboard_module_imports_without_starting_network():
    from crypto_analyst.dashboard import CryptoDashboard

    assert CryptoDashboard.__name__ == "CryptoDashboard"


def test_desktop_has_crypto_analyst_navigation_and_workspace_action():
    root = Path(__file__).resolve().parents[1]
    source = (root / "jarvis_desktop.py").read_text(encoding="utf-8")
    assert "CRYPTO ANALYST / PAPER" in source
    assert "def show_crypto_analyst(self):" in source
    assert "from crypto_analyst.dashboard import CryptoDashboard" in source
