from pathlib import Path

import pytest

from agent.tools import self_modify


def test_write_and_rollback_restores_nested_path_with_underscores(tmp_path, monkeypatch):
    root = tmp_path / "project"
    target = root / "agent" / "some_file_with_under_scores.py"
    target.parent.mkdir(parents=True)
    target.write_text("original = True\n", encoding="utf-8")
    backups = root / ".jarvis_backups"
    monkeypatch.setattr(self_modify, "ROOT", root)
    monkeypatch.setattr(self_modify, "BACKUP_ROOT", backups)

    self_modify.write_source("agent/some_file_with_under_scores.py", "changed = True\n")
    assert target.read_text(encoding="utf-8") == "changed = True\n"

    result = self_modify.rollback_last_backup()
    assert "agent/some_file_with_under_scores.py" in result
    assert target.read_text(encoding="utf-8") == "original = True\n"


def test_new_file_does_not_create_a_fake_backup(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(self_modify, "ROOT", root)
    monkeypatch.setattr(self_modify, "BACKUP_ROOT", root / ".jarvis_backups")

    result = self_modify.write_source("new_module.py", "value = 1\n")
    assert "резервная копия не создавалась" in result
    with pytest.raises(FileNotFoundError, match="Нет резервных копий"):
        self_modify.rollback_last_backup()


def test_rollback_refuses_path_outside_project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    target = root / "safe.py"
    root.mkdir()
    target.write_text("safe = True\n", encoding="utf-8")
    backups = root / ".jarvis_backups"
    backups.mkdir()
    (backups / "20261012_120000_000001__%2E%2E%2Foutside.py").write_text(
        "unsafe = True\n", encoding="utf-8"
    )
    monkeypatch.setattr(self_modify, "ROOT", root)
    monkeypatch.setattr(self_modify, "BACKUP_ROOT", backups)

    with pytest.raises(ValueError, match="Путь выходит за пределы проекта"):
        self_modify.rollback_last_backup()
