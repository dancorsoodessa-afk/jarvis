"""Контролируемый цикл самоулучшения JARVIS.

JARVIS никогда не изменяет код самовольно: проблема -> предложение -> тест ->
подтверждение пользователя -> применение -> повторная проверка -> сохранение.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any


@dataclass
class ImprovementProposal:
    problem: str
    change: str
    tests: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    status: str = "proposed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SelfImprovementManager:
    """Безопасный журнал и state-machine для управляемого самоулучшения."""

    STATES = ("proposed", "tested", "awaiting_confirmation", "applied", "verified", "saved", "rejected")

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "self_improvements.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def propose(self, problem: str, change: str, tests: list[str] | None = None) -> ImprovementProposal:
        return ImprovementProposal(problem=problem, change=change, tests=tests or [])

    def mark_tested(self, proposal: ImprovementProposal, evidence: dict[str, Any]) -> None:
        proposal.evidence = evidence
        proposal.status = "tested"

    def request_confirmation(self, proposal: ImprovementProposal) -> None:
        if proposal.status != "tested":
            raise ValueError("Изменение нельзя подтверждать до успешного тестирования")
        proposal.status = "awaiting_confirmation"

    def confirm(self, proposal: ImprovementProposal, approved: bool) -> None:
        if proposal.status != "awaiting_confirmation":
            raise ValueError("Изменение не ожидает подтверждения")
        proposal.status = "applied" if approved else "rejected"

    def mark_verified(self, proposal: ImprovementProposal, evidence: dict[str, Any]) -> None:
        if proposal.status != "applied":
            raise ValueError("Проверять можно только применённое изменение")
        proposal.evidence.update(evidence)
        proposal.status = "verified"

    def save(self, proposal: ImprovementProposal) -> None:
        if proposal.status != "verified":
            raise ValueError("Сохранять можно только проверенное улучшение")
        records: list[dict[str, Any]] = []
        if self.path.exists():
            try:
                records = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                records = []
        records.append({
            "problem": proposal.problem,
            "change": proposal.change,
            "tests": proposal.tests,
            "evidence": proposal.evidence,
            "status": "saved",
            "created_at": proposal.created_at,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })
        self.path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        proposal.status = "saved"
