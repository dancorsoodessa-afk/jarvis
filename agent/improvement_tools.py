"""Persistent, explicit approval workflow for SUPERMAN self-improvement.

The workflow records proposals and evidence. It never edits source files by itself:
the agent must use the source-editing tool after the user approves a proposal.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_PATH = Path.home() / ".superman" / "improvement_workflow.json"
_LOCK = threading.RLock()
_STATES = {"proposed", "tested", "awaiting_confirmation", "approved", "applied", "verified", "saved", "rejected"}


def _load() -> dict[str, dict]:
    if not _PATH.exists():
        return {}
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, dict]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_PATH.parent, prefix="improvements.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _get(data: dict[str, dict], proposal_id: str, expected: str) -> dict:
    item = data.get(str(proposal_id).strip())
    if item is None:
        raise ValueError("Предложение не найдено")
    if item.get("status") != expected:
        raise ValueError(f"Недопустимый переход: сейчас {item.get('status')}, ожидалось {expected}")
    return item


def propose_improvement(problem: str, change: str, tests: str = "") -> str:
    problem, change = str(problem).strip(), str(change).strip()
    if not problem or not change:
        raise ValueError("Опишите проблему и предлагаемое изменение")
    with _LOCK:
        data = _load()
        proposal_id = uuid.uuid4().hex[:10]
        data[proposal_id] = {
            "id": proposal_id, "problem": problem[:3000], "change": change[:5000],
            "tests": str(tests).strip()[:2000], "status": "proposed",
            "created_at": datetime.now(timezone.utc).isoformat(), "evidence": [],
        }
        _save(data)
    return f"Создано предложение {proposal_id}. Сначала внеси изменение в отдельной рабочей копии и запусти тесты; подтверждение пользователя обязательно до применения."


def mark_improvement_tested(proposal_id: str, evidence: str) -> str:
    evidence = str(evidence).strip()
    if not evidence:
        raise ValueError("Добавьте фактический результат тестирования")
    with _LOCK:
        data = _load()
        item = _get(data, proposal_id, "proposed")
        item["evidence"].append({"stage": "tests", "details": evidence[:5000], "at": datetime.now(timezone.utc).isoformat()})
        item["status"] = "tested"
        _save(data)
    return f"Предложение {proposal_id}: результат тестов записан. Теперь запроси подтверждение пользователя."


def request_improvement_confirmation(proposal_id: str) -> str:
    with _LOCK:
        data = _load()
        item = _get(data, proposal_id, "tested")
        item["status"] = "awaiting_confirmation"
        _save(data)
    return f"Предложение {proposal_id} ожидает явного подтверждения пользователя. Не изменяй код, пока пользователь не согласится."


def confirm_improvement(proposal_id: str, approved: str) -> str:
    decision = str(approved).strip().casefold()
    if decision not in {"yes", "no", "да", "нет", "true", "false"}:
        raise ValueError("Укажите approved как да/нет")
    allow = decision in {"yes", "да", "true"}
    with _LOCK:
        data = _load()
        item = _get(data, proposal_id, "awaiting_confirmation")
        item["status"] = "approved" if allow else "rejected"
        item["evidence"].append({"stage": "user_decision", "details": "approved" if allow else "rejected", "at": datetime.now(timezone.utc).isoformat()})
        _save(data)
    return f"Предложение {proposal_id}: " + ("одобрено. Теперь можно применить описанное изменение, затем запустить тесты." if allow else "отклонено; код менять нельзя.")


def mark_improvement_applied(proposal_id: str, summary: str) -> str:
    summary = str(summary).strip()
    if not summary:
        raise ValueError("Опишите, какое изменение действительно применено")
    with _LOCK:
        data = _load()
        item = _get(data, proposal_id, "approved")
        item["evidence"].append({"stage": "applied", "details": summary[:5000], "at": datetime.now(timezone.utc).isoformat()})
        item["status"] = "applied"
        _save(data)
    return f"Применение предложения {proposal_id} записано. Теперь запусти тесты и укажи их реальный результат."


def verify_improvement(proposal_id: str, evidence: str) -> str:
    evidence = str(evidence).strip()
    if not evidence:
        raise ValueError("Укажите результат повторной проверки")
    with _LOCK:
        data = _load()
        item = _get(data, proposal_id, "applied")
        item["evidence"].append({"stage": "verification", "details": evidence[:5000], "at": datetime.now(timezone.utc).isoformat()})
        item["status"] = "verified"
        _save(data)
    return f"Предложение {proposal_id} проверено. Можно сохранить результат в журнал."


def save_improvement(proposal_id: str) -> str:
    with _LOCK:
        data = _load()
        item = _get(data, proposal_id, "verified")
        item["status"] = "saved"
        item["saved_at"] = datetime.now(timezone.utc).isoformat()
        _save(data)
    return f"Улучшение {proposal_id} сохранено в журнале СУПЕРМЕН."
