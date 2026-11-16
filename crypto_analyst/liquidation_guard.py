"""Estimated liquidation-distance guard for linear isolated paper positions."""

from __future__ import annotations

from decimal import Decimal


def estimate_linear_liquidation_price(
    entry: Decimal,
    side: str,
    leverage: Decimal,
    maintenance_margin_rate: Decimal = Decimal("0.005"),
) -> Decimal:
    """Approximation only; this is not the exchange liquidation engine."""
    if entry <= 0 or leverage < 1:
        raise ValueError("entry must be positive and leverage must be >= 1.")
    if not (Decimal("0") <= maintenance_margin_rate < Decimal("0.5")):
        raise ValueError("maintenance margin rate is outside the supported range.")
    if side == "buy":
        factor = Decimal("1") - Decimal("1") / leverage + maintenance_margin_rate
    elif side == "sell":
        factor = Decimal("1") + Decimal("1") / leverage - maintenance_margin_rate
    else:
        raise ValueError("side must be buy or sell.")
    return entry * factor


def stop_is_clear_of_liquidation(
    entry: Decimal,
    stop_loss: Decimal,
    side: str,
    leverage: Decimal,
    maintenance_margin_rate: Decimal = Decimal("0.005"),
    buffer_fraction: Decimal = Decimal("0.2"),
) -> bool:
    if not (Decimal("0") <= buffer_fraction < Decimal("1")):
        raise ValueError("buffer_fraction must be in [0, 1).")
    liquidation = estimate_linear_liquidation_price(
        entry, side, leverage, maintenance_margin_rate
    )
    if side == "buy":
        distance = entry - liquidation
        return stop_loss > liquidation + distance * buffer_fraction
    distance = liquidation - entry
    return stop_loss < liquidation - distance * buffer_fraction
