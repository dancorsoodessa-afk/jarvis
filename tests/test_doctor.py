from agent.doctor import run


def test_doctor_openai_compatible_can_pass_without_starting_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY", str(tmp_path / "memory.json"))
    monkeypatch.setenv("JARVIS_PROVIDER", "openai-compatible")
    ok, lines = run("openai-compatible")
    assert ok is True
    assert any("OpenAI-compatible" in line for line in lines)
    assert lines[-1] == "Итог: ГОТОВ"


def test_doctor_airllm_reports_missing_model(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY", str(tmp_path / "memory.json"))
    monkeypatch.setenv("JARVIS_AIRLLM_MODEL", "")
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None if name == "airllm" else object())
    ok, lines = run("airllm")
    assert ok is False
    assert any("AirLLM не установлен" in line for line in lines)
    assert any("JARVIS_AIRLLM_MODEL" in line for line in lines)
