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


def cumulative_volume_delta(trades) -> tuple[Decimal, ...]:
    """Return cumulative aggressor-side volume delta in trade arrival order."""
    running = ZERO
    result = []
    for trade in trades:
        running += trade.amount if trade.side == "buy" else -trade.amount
        result.append(running)
    return tuple(result)


def large_trades(trades, minimum_notional: Decimal):
    """Return prints whose price * amount reaches the configured quote notional."""
    if not minimum_notional.is_finite() or minimum_notional <= 0:
        raise ValueError("minimum_notional must be positive and finite.")
    return [
        trade for trade in trades
        if trade.price * trade.amount >= minimum_notional
    ]


def probable_iceberg(trades, minimum_repeated_volume: Decimal) -> bool:
    """Weak hidden-liquidity heuristic: several smaller prints repeatedly execute at one price."""
    if not minimum_repeated_volume.is_finite() or minimum_repeated_volume <= 0:
        raise ValueError("minimum_repeated_volume must be positive and finite.")
    by_price: dict[Decimal, list[Decimal]] = {}
    for trade in trades:
        by_price.setdefault(trade.price, []).append(trade.amount)
    return any(
        len(amounts) >= 3
        and sum(amounts, ZERO) >= minimum_repeated_volume
        and max(amounts) <= sum(amounts, ZERO) / Decimal("2")
        for amounts in by_price.values()
    )
