"""Typed market and signal models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_value(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("Market values must be finite.")
    return result


@dataclass(frozen=True)
class Level:
    price: Decimal
    amount: Decimal

    @classmethod
    def from_okx(cls, row: list[Any] | tuple[Any, ...]) -> "Level":
        if len(row) < 2:
            raise ValueError("Order-book level must contain price and amount.")
        price, amount = decimal_value(row[0]), decimal_value(row[1])
        if price <= 0 or amount < 0:
            raise ValueError("Order-book price must be positive and amount non-negative.")
        return cls(price=price, amount=amount)


@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]
    timestamp_ms: int
    received_at_ms: int
    sequence_id: int | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol is required.")
        if not self.bids or not self.asks:
            raise ValueError("Both sides of the order book are required.")
        if self.timestamp_ms <= 0 or self.received_at_ms <= 0:
            raise ValueError("Timestamps must be positive.")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("Crossed or locked order book is not accepted.")
        if tuple(sorted(self.bids, key=lambda x: x.price, reverse=True)) != self.bids:
            raise ValueError("Bids must be sorted from highest to lowest.")
        if tuple(sorted(self.asks, key=lambda x: x.price)) != self.asks:
            raise ValueError("Asks must be sorted from lowest to highest.")

    @property
    def best_bid(self) -> Decimal:
        return self.bids[0].price

    @property
    def best_ask(self) -> Decimal:
        return self.asks[0].price

    @property
    def mid_price(self) -> Decimal:
        return (self.best_bid + self.best_ask) / Decimal("2")

    @property
    def spread_bps(self) -> Decimal:
        if self.mid_price <= 0:
            return Decimal("Infinity")
        return (self.best_ask - self.best_bid) / self.mid_price * Decimal("10000")

    @classmethod
    def from_okx(
        cls,
        symbol: str,
        payload: dict[str, Any],
        received_at_ms: int,
    ) -> "OrderBookSnapshot":
        bids = tuple(Level.from_okx(row) for row in payload.get("bids", []))
        asks = tuple(Level.from_okx(row) for row in payload.get("asks", []))
        return cls(
            symbol=symbol,
            bids=tuple(sorted(bids, key=lambda x: x.price, reverse=True)),
            asks=tuple(sorted(asks, key=lambda x: x.price)),
            timestamp_ms=int(payload["ts"]),
            received_at_ms=received_at_ms,
            sequence_id=int(payload["seqId"]) if payload.get("seqId") is not None else None,
        )


@dataclass(frozen=True)
class MarketTrade:
    symbol: str
    side: str
    price: Decimal
    amount: Decimal
    timestamp_ms: int
    trade_id: str = ""

    def __post_init__(self) -> None:
        if self.side not in {"buy", "sell"}:
            raise ValueError("Trade side must be buy or sell.")
        if self.price <= 0 or self.amount <= 0:
            raise ValueError("Trade price and amount must be positive.")
        if self.timestamp_ms <= 0:
            raise ValueError("Trade timestamp must be positive.")

    @classmethod
    def from_okx(cls, symbol: str, payload: dict[str, Any]) -> "MarketTrade":
        return cls(
            symbol=symbol,
            side=str(payload["side"]).lower(),
            price=decimal_value(payload["px"]),
            amount=decimal_value(payload["sz"]),
            timestamp_ms=int(payload["ts"]),
            trade_id=str(payload.get("tradeId", "")),
        )


@dataclass(frozen=True)
class TradingSignal:
    symbol: str
    side: str
    entry: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    imbalance: Decimal
    trade_delta: Decimal
    spread_bps: Decimal
    created_at_ms: int
    reason: str

    def __post_init__(self) -> None:
        if self.side not in {"buy", "sell"}:
            raise ValueError("Signal side must be buy or sell.")
        if self.entry <= 0 or self.stop_loss <= 0 or self.take_profit <= 0:
            raise ValueError("Signal prices must be positive.")
        if self.created_at_ms <= 0:
            raise ValueError("Signal timestamp must be positive.")
