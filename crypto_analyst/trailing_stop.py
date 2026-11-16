"""Monotonic trailing-stop updates for virtual positions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class TrailingStopManager:
    def __init__(self, distance_bps: Decimal = Decimal("30")):
        if not distance_bps.is_finite() or distance_bps <= 0:
            raise ValueError("Trailing-stop distance must be positive and finite.")
        self.distance_bps = distance_bps

    def update(self, position: Any, market_price: Decimal) -> Decimal:
        if position.status != "open" or market_price <= 0:
            return position.stop_loss
        favorable = position.favorable_price or position.entry_price
        fraction = self.distance_bps / Decimal("10000")
        if position.side == "buy":
            if market_price > favorable:
                favorable = market_price
                position.favorable_price = favorable
            if favorable > position.entry_price:
                candidate = favorable * (Decimal("1") - fraction)
                if candidate > position.stop_loss:
                    position.stop_loss = candidate
        elif position.side == "sell":
            if market_price < favorable:
                favorable = market_price
                position.favorable_price = favorable
            if favorable < position.entry_price:
                candidate = favorable * (Decimal("1") + fraction)
                if candidate < position.stop_loss:
                    position.stop_loss = candidate
        else:
            raise ValueError("Position side must be buy or sell.")
        return position.stop_loss
