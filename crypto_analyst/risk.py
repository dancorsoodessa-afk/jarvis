"""Deterministic risk gate for paper positions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import TradingSignal


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: Decimal = Decimal("0.005")
    max_daily_loss: Decimal = Decimal("0.02")
    max_open_positions: int = 2
    min_reward_risk: Decimal = Decimal("1.5")
    max_spread_bps: Decimal = Decimal("8")
    max_data_age_ms: int = 1_500
    max_leverage: Decimal = Decimal("2")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    quantity: Decimal = Decimal("0")
    reason: str = ""


class RiskManager:
    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()
        if not (Decimal("0") < self.config.risk_per_trade <= Decimal("0.01")):
            raise ValueError("risk_per_trade must be in (0, 1%].")
        if not (Decimal("0") < self.config.max_daily_loss <= Decimal("0.05")):
            raise ValueError("max_daily_loss must be in (0, 5%].")
        if self.config.max_open_positions < 1:
            raise ValueError("max_open_positions must be positive.")

    def approve(
        self,
        signal: TradingSignal,
        equity: Decimal,
        daily_pnl: Decimal,
        open_positions: int,
        now_ms: int,
        data_timestamp_ms: int,
    ) -> RiskDecision:
        if equity <= 0:
            return RiskDecision(False, reason="Virtual equity is not positive.")
        if open_positions >= self.config.max_open_positions:
            return RiskDecision(False, reason="Maximum open positions reached.")
        if daily_pnl <= -(equity * self.config.max_daily_loss):
            return RiskDecision(False, reason="Daily loss limit reached.")
        if signal.spread_bps > self.config.max_spread_bps:
            return RiskDecision(False, reason="Spread exceeds configured limit.")
        age = now_ms - data_timestamp_ms
        if age < 0 or age > self.config.max_data_age_ms:
            return RiskDecision(False, reason="Market data is stale or timestamp is invalid.")

        risk_distance = abs(signal.entry - signal.stop_loss)
        reward_distance = abs(signal.take_profit - signal.entry)
        if risk_distance <= 0:
            return RiskDecision(False, reason="Stop-loss distance is zero.")
        reward_risk = reward_distance / risk_distance
        if reward_risk < self.config.min_reward_risk:
            return RiskDecision(False, reason="Reward/risk ratio is below minimum.")

        risk_budget = equity * self.config.risk_per_trade
        quantity = risk_budget / risk_distance
        max_notional = equity * self.config.max_leverage
        quantity = min(quantity, max_notional / signal.entry)
        if quantity <= 0:
            return RiskDecision(False, reason="Calculated position size is zero.")
        return RiskDecision(True, quantity=quantity, reason="Approved for paper trading.")
