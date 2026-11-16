"""Deterministic paper-trading risk gate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .liquidation_guard import stop_is_clear_of_liquidation
from .models import TradingSignal


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: Decimal = Decimal("0.005")
    max_daily_loss: Decimal = Decimal("0.02")
    max_open_positions: int = 2
    min_reward_risk: Decimal = Decimal("1.5")
    max_spread_bps: Decimal = Decimal("8")
    max_slippage_bps: Decimal = Decimal("5")
    max_data_age_ms: int = 1_500
    max_leverage: Decimal = Decimal("2")
    maintenance_margin_rate: Decimal = Decimal("0.005")
    liquidation_buffer_fraction: Decimal = Decimal("0.2")


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
        if (
            self.config.min_reward_risk < 1
            or self.config.max_spread_bps <= 0
            or self.config.max_slippage_bps <= 0
            or self.config.max_data_age_ms < 1
            or self.config.max_leverage < 1
        ):
            raise ValueError("Reward/risk, spread, slippage, age, or leverage limit is invalid.")
        if not (
            Decimal("0") <= self.config.maintenance_margin_rate < Decimal("0.5")
            and Decimal("0") <= self.config.liquidation_buffer_fraction < Decimal("1")
        ):
            raise ValueError("Liquidation guard configuration is invalid.")

    def approve(
        self,
        signal: TradingSignal,
        equity: Decimal,
        daily_pnl: Decimal,
        open_positions: int,
        now_ms: int,
        data_timestamp_ms: int,
        unit_multiplier: Decimal = Decimal("1"),
        leverage: Decimal | None = None,
        estimated_slippage_bps: Decimal | None = None,
    ) -> RiskDecision:
        if not equity.is_finite() or equity <= 0:
            return RiskDecision(False, reason="Virtual equity is not positive and finite.")
        if not daily_pnl.is_finite():
            return RiskDecision(False, reason="Daily PnL is not finite.")
        if open_positions >= self.config.max_open_positions:
            return RiskDecision(False, reason="Maximum open positions reached.")
        if daily_pnl <= -(equity * self.config.max_daily_loss):
            return RiskDecision(False, reason="Daily loss limit reached.")
        if signal.spread_bps > self.config.max_spread_bps:
            return RiskDecision(False, reason="Spread exceeds configured limit.")
        if estimated_slippage_bps is not None and (
            not estimated_slippage_bps.is_finite()
            or estimated_slippage_bps > self.config.max_slippage_bps
        ):
            return RiskDecision(False, reason="Estimated slippage exceeds configured limit.")

        age = now_ms - data_timestamp_ms
        if age < 0 or age > self.config.max_data_age_ms:
            return RiskDecision(False, reason="Market data is stale or timestamp is invalid.")
        if not unit_multiplier.is_finite() or unit_multiplier <= 0:
            return RiskDecision(False, reason="Instrument unit multiplier is invalid.")

        if signal.side == "buy":
            if not (signal.stop_loss < signal.entry < signal.take_profit):
                return RiskDecision(False, reason="LONG stop/target geometry is invalid.")
        elif signal.side == "sell":
            if not (signal.take_profit < signal.entry < signal.stop_loss):
                return RiskDecision(False, reason="SHORT stop/target geometry is invalid.")
        else:
            return RiskDecision(False, reason="Signal side is invalid.")

        if leverage is not None:
            if not leverage.is_finite() or leverage < 1 or leverage > self.config.max_leverage:
                return RiskDecision(False, reason="Requested leverage is outside configured limits.")
            if not stop_is_clear_of_liquidation(
                signal.entry,
                signal.stop_loss,
                signal.side,
                leverage,
                self.config.maintenance_margin_rate,
                self.config.liquidation_buffer_fraction,
            ):
                return RiskDecision(False, reason="Stop loss is too close to estimated liquidation.")

        risk_distance = abs(signal.entry - signal.stop_loss)
        reward_distance = abs(signal.take_profit - signal.entry)
        if risk_distance <= 0:
            return RiskDecision(False, reason="Stop-loss distance is zero.")
        reward_risk = reward_distance / risk_distance
        if reward_risk < self.config.min_reward_risk:
            return RiskDecision(False, reason="Reward/risk ratio is below minimum.")

        risk_budget = equity * self.config.risk_per_trade
        risk_per_unit = risk_distance * unit_multiplier
        notional_per_unit = signal.entry * unit_multiplier
        quantity = risk_budget / risk_per_unit
        max_notional = equity * self.config.max_leverage
        quantity = min(quantity, max_notional / notional_per_unit)
        if not quantity.is_finite() or quantity <= 0:
            return RiskDecision(False, reason="Calculated position size is invalid.")
        return RiskDecision(True, quantity=quantity, reason="Risk checks passed.")
