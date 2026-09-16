import pytest

from agent.tools import commands


def test_parse_rejects_unknown_command():
    with pytest.raises(ValueError, match="Команда запрещена"):
        commands._parse("powershell.exe -Command whoami")


def test_parse_allows_readonly_command():
    assert commands._parse("whoami.exe")[0] == "whoami.exe"


def test_run_never_uses_shell(monkeypatch):
    monkeypatch.setattr(commands.os, "name", "nt")
    captured = {}

    class Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return Proc()

    monkeypatch.setattr(commands.subprocess, "run", fake_run)
    assert commands.run("whoami.exe") == "ok"
    assert captured["shell"] is False
