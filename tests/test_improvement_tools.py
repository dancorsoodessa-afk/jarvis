from agent import improvement_tools


def test_persistent_self_improvement_requires_approval_and_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(improvement_tools, "_PATH", tmp_path / "workflow.json")
    created = improvement_tools.propose_improvement("bug", "fix", "pytest")
    proposal_id = created.split()[2].rstrip(".")
    improvement_tools.mark_improvement_tested(proposal_id, "pytest: 3 passed")
    improvement_tools.request_improvement_confirmation(proposal_id)

    assert "одобрено" in improvement_tools.confirm_improvement(proposal_id, "да")
    improvement_tools.mark_improvement_applied(proposal_id, "Изменён файл после одобрения")
    improvement_tools.verify_improvement(proposal_id, "pytest: 4 passed")
    assert "сохранено" in improvement_tools.save_improvement(proposal_id)

    import json
    saved = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert saved[proposal_id]["status"] == "saved"


def test_self_improvement_cannot_skip_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(improvement_tools, "_PATH", tmp_path / "workflow.json")
    created = improvement_tools.propose_improvement("bug", "fix")
    proposal_id = created.split()[2].rstrip(".")
    improvement_tools.mark_improvement_tested(proposal_id, "tests passed")

    try:
        improvement_tools.mark_improvement_applied(proposal_id, "applied without approval")
    except ValueError:
        pass
    else:
        raise AssertionError("workflow must reject applying without explicit approval")
