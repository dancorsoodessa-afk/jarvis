"""Order-book microstructure features."""

from __future__ import annotations

from decimal import Decimal
from statistics import median

from .models import OrderBookSnapshot


ZERO = Decimal("0")


def _weighted_volume(levels, depth: int) -> Decimal:
    """Give near-touch levels more weight than distant levels."""
    if not levels:
        return ZERO
    best = levels[0].price
    total = ZERO
    for level in levels[:depth]:
        distance_bps = abs(level.price - best) / best * Decimal("10000")
        weight = Decimal("1") / (Decimal("1") + distance_bps)
        total += level.amount * weight
    return total


def bid_ask_imbalance(book: OrderBookSnapshot, depth: int = 10) -> Decimal:
    """Return weighted imbalance in [-1, 1]."""
    if depth < 1:
        raise ValueError("depth must be positive.")
    bid_volume = _weighted_volume(book.bids, depth)
    ask_volume = _weighted_volume(book.asks, depth)
    total = bid_volume + ask_volume
    if total == 0:
        return ZERO
    return (bid_volume - ask_volume) / total


def liquidity_walls(
    book: OrderBookSnapshot,
    depth: int = 20,
    multiple: Decimal = Decimal("3"),
) -> dict[str, list[dict[str, Decimal]]]:
    """Find unusually large visible levels; this does not prove genuine support/resistance."""
    if depth < 3 or multiple <= 1:
        raise ValueError("depth must be >= 3 and multiple must be > 1.")

    def scan(levels):
        volumes = [float(level.amount) for level in levels[:depth]]
        baseline = Decimal(str(median(volumes))) if volumes else ZERO
        if baseline <= 0:
            return []
        found = []
        for level in levels[:depth]:
            ratio = level.amount / baseline
            if ratio >= multiple:
                found.append({
                    "price": level.price,
                    "amount": level.amount,
                    "ratio": ratio,
                })
        return found

    return {"bids": scan(book.bids), "asks": scan(book.asks)}


def trade_delta(trades) -> Decimal:
    """Aggressor-side volume delta for the supplied trade window."""
    result = ZERO
    for trade in trades:
        result += trade.amount if trade.side == "buy" else -trade.amount
    return result


def probable_iceberg(trades, minimum_repeated_volume: Decimal) -> bool:
    """Heuristic only: repeated executions at one price; never claims hidden size is known."""
    if minimum_repeated_volume <= 0:
        raise ValueError("minimum_repeated_volume must be positive.")
    by_price: dict[Decimal, Decimal] = {}
    for trade in trades:
        by_price[trade.price] = by_price.get(trade.price, ZERO) + trade.amount
    return any(volume >= minimum_repeated_volume for volume in by_price.values())
