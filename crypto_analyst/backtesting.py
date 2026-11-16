"""Chronological event replay and initial paper-performance metrics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from .runtime import PaperScalpingRuntime


@dataclass(frozen=True)
class BacktestReport:
    trade_count: int
    wins: int
    losses: int
    win_rate: float
    net_profit: Decimal
    profit_factor: float
    max_drawdown: Decimal
    average_trade: Decimal


def performance_report(
    trade_pnls: Iterable[Decimal],
    starting_equity: Decimal = Decimal("10000"),
) -> BacktestReport:
    if not starting_equity.is_finite() or starting_equity <= 0:
        raise ValueError("starting_equity must be positive and finite.")
    pnls = list(trade_pnls)
    if any(not value.is_finite() for value in pnls):
        raise ValueError("Trade PnL values must be finite.")
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    gross_wins = sum(wins, Decimal("0"))
    gross_losses = abs(sum(losses, Decimal("0")))
    profit_factor = (
        float(gross_wins / gross_losses)
        if gross_losses else (float("inf") if gross_wins else 0.0)
    )
    equity = peak = starting_equity
    max_drawdown = Decimal("0")
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    count = len(pnls)
    net = sum(pnls, Decimal("0"))
    return BacktestReport(
        count, len(wins), len(losses), len(wins) / count if count else 0.0,
        net, profit_factor, max_drawdown,
        net / count if count else Decimal("0"),
    )


class MarketReplayEngine:
    """Replays stored raw market events; out-of-order input is rejected."""

    def replay(
        self, events: Iterable[dict[str, Any]], runtime: PaperScalpingRuntime
    ) -> tuple[list, BacktestReport]:
        signals = []
        previous_timestamp = -1
        for event in events:
            timestamp = int(event["received_at_ms"])
            if timestamp < previous_timestamp:
                raise ValueError("Replay events must be chronological; look-ahead is forbidden.")
            previous_timestamp = timestamp
            signals.extend(runtime.on_market_message(event["message"], timestamp))
        pnls = [
            position.realized_pnl
            for position in runtime.broker.positions.values()
            if position.status == "closed"
        ]
        return signals, performance_report(pnls, runtime.broker.initial_balance)
