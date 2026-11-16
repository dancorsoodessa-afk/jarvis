"""Visible-depth VWAP slippage estimator."""

from __future__ import annotations

from decimal import Decimal

from .models import OrderBookSnapshot


def estimate_book_slippage_bps(
    book: OrderBookSnapshot, side: str, quantity: Decimal
) -> Decimal | None:
    """Return touch-relative depth slippage; None means the book is too shallow."""
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell.")
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("quantity must be positive and finite.")
    levels = book.asks if side == "buy" else book.bids
    touch = levels[0].price
    remaining = quantity
    total_value = Decimal("0")
    filled = Decimal("0")
    for level in levels:
        amount = min(remaining, level.amount)
        if amount <= 0:
            continue
        total_value += amount * level.price
        filled += amount
        remaining -= amount
        if remaining <= 0:
            break
    if remaining > 0 or filled <= 0:
        return None
    vwap = total_value / filled
    if side == "buy":
        return (vwap - touch) / touch * Decimal("10000")
    return (touch - vwap) / touch * Decimal("10000")
