"""In-memory normalized OKX market state."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from .models import MarketTrade, OrderBookSnapshot


@dataclass(frozen=True)
class TickerSnapshot:
    symbol: str
    last: str
    bid: str
    ask: str
    timestamp_ms: int
    received_at_ms: int


class MarketState:
    def __init__(self, trade_buffer_size: int = 2_000):
        if trade_buffer_size < 1:
            raise ValueError("trade_buffer_size must be positive.")
        self.orderbooks: dict[str, OrderBookSnapshot] = {}
        self.trades: dict[str, deque[MarketTrade]] = defaultdict(
            lambda: deque(maxlen=trade_buffer_size)
        )
        self.tickers: dict[str, TickerSnapshot] = {}
        self.open_interest: dict[str, dict[str, Any]] = {}
        self.funding_rates: dict[str, dict[str, Any]] = {}
        self.liquidations: deque[dict[str, Any]] = deque(maxlen=2_000)

    def on_okx_message(self, message: dict[str, Any], received_at_ms: int) -> None:
        arg = message.get("arg") or {}
        channel = str(arg.get("channel") or "")
        symbol = str(arg.get("instId") or "")
        if not symbol and channel != "liquidation-orders":
            return
        rows = message.get("data") or []
        if not isinstance(rows, list):
            return

        if channel == "books5":
            for row in rows:
                try:
                    self.orderbooks[symbol] = OrderBookSnapshot.from_okx(
                        symbol, row, received_at_ms
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        elif channel == "trades":
            for row in rows:
                try:
                    self.trades[symbol].append(MarketTrade.from_okx(symbol, row))
                except (KeyError, TypeError, ValueError):
                    continue
        elif channel == "tickers":
            for row in rows:
                try:
                    self.tickers[symbol] = TickerSnapshot(
                        symbol=symbol,
                        last=str(row["last"]),
                        bid=str(row.get("bidPx") or ""),
                        ask=str(row.get("askPx") or ""),
                        timestamp_ms=int(row["ts"]),
                        received_at_ms=received_at_ms,
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        elif channel == "open-interest":
            for row in rows:
                if isinstance(row, dict):
                    self.open_interest[symbol] = dict(row)
        elif channel == "funding-rate":
            for row in rows:
                if isinstance(row, dict):
                    self.funding_rates[symbol] = dict(row)
        elif channel == "liquidation-orders":
            for row in rows:
                if not isinstance(row, dict):
                    continue
                instrument_id = str(row.get("instId") or symbol)
                for detail in row.get("details") or []:
                    if isinstance(detail, dict):
                        self.liquidations.append({
                            "symbol": instrument_id,
                            "received_at_ms": received_at_ms,
                            **detail,
                        })

    def recent_trades(self, symbol: str, since_ms: int | None = None) -> list[MarketTrade]:
        rows = list(self.trades.get(symbol, ()))
        if since_ms is None:
            return rows
        return [trade for trade in rows if trade.timestamp_ms >= since_ms]
