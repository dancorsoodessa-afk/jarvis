"""Whale-following signal filter. Signals are candidates for Paper Broker only."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import MarketTrade, OrderBookSnapshot, TradingSignal
from .orderbook import bid_ask_imbalance, trade_delta


def _timestamp_ms(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        number = int(float(text))
        return number * 1000 if number < 10_000_000_000 else number
    except (ValueError, TypeError):
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return int(parsed.timestamp() * 1000)
    except (ValueError, TypeError, OverflowError):
        return 0


class WhaleCopyEngine:
    """Require a ranked wallet, fresh fill and matching OKX order-flow confirmation."""

    def __init__(
        self,
        whitelist: set[str] | None = None,
        min_whale_notional_usd: Decimal = Decimal("250000"),
        max_whale_age_ms: int = 30_000,
        min_imbalance: Decimal = Decimal("0.15"),
        stop_distance_bps: Decimal = Decimal("40"),
        reward_risk: Decimal = Decimal("1.8"),
        max_spread_bps: Decimal = Decimal("8"),
    ):
        if min_whale_notional_usd <= 0 or max_whale_age_ms < 1:
            raise ValueError("Whale notional and freshness limits must be positive.")
        if not Decimal("0") < min_imbalance < Decimal("1"):
            raise ValueError("min_imbalance must be between zero and one.")
        if stop_distance_bps <= 0 or reward_risk < Decimal("1.5"):
            raise ValueError("Whale-copy stop and reward/risk are too small.")
        self.whitelist = set(whitelist or ())
        self.min_whale_notional_usd = min_whale_notional_usd
        self.max_whale_age_ms = max_whale_age_ms
        self.min_imbalance = min_imbalance
        self.stop_distance_bps = stop_distance_bps
        self.reward_risk = reward_risk
        self.max_spread_bps = max_spread_bps

    @staticmethod
    def _direction(whale_trade: Any) -> str | None:
        raw = getattr(whale_trade, "raw", {}) or {}
        if raw.get("position_action") is not None:
            # CoinGlass position alerts are not individual fills.
            return None
        action = str(raw.get("action") or "").lower()
        if any(word in action for word in ("close", "reduce", "liquidat")):
            return None
        if "open long" in action or "add long" in action:
            return "buy"
        if "open short" in action or "add short" in action:
            return "sell"
        side = str(getattr(whale_trade, "side", "")).lower()
        if side in {"buy", "long", "bullish"}:
            return "buy"
        if side in {"sell", "short", "bearish"}:
            return "sell"
        return None

    def evaluate(
        self,
        whale_trade: Any,
        tracked_wallets: set[str],
        book: OrderBookSnapshot | None,
        recent_trades: list[MarketTrade],
        now_ms: int,
    ) -> TradingSignal | None:
        address = str(getattr(whale_trade, "address", "")).lower()
        if not address or address not in {item.lower() for item in tracked_wallets}:
            return None
        if book is None or (self.whitelist and book.symbol not in self.whitelist):
            return None
        coin = str(getattr(whale_trade, "coin", "")).upper()
        if not coin or book.symbol.split("-")[0].upper() != coin:
            return None
        raw = getattr(whale_trade, "raw", {}) or {}
        timestamp_ms = _timestamp_ms(getattr(whale_trade, "timestamp", ""))
        age = now_ms - timestamp_ms
        if timestamp_ms <= 0 or age < 0 or age > self.max_whale_age_ms:
            return None
        try:
            notional = Decimal(str(getattr(whale_trade, "size_usd", "0")))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not notional.is_finite() or notional < self.min_whale_notional_usd:
            return None
        if now_ms - book.received_at_ms < 0 or now_ms - book.received_at_ms > 1_500:
            return None
        if book.spread_bps > self.max_spread_bps:
            return None

        side = self._direction(whale_trade)
        if side is None:
            return None
        recent = [
            trade for trade in recent_trades
            if trade.symbol == book.symbol
            and 0 <= now_ms - trade.timestamp_ms <= 1_500
        ]
        if not recent:
            return None
        imbalance = bid_ask_imbalance(book, depth=min(10, len(book.bids), len(book.asks)))
        delta = trade_delta(recent)
        if side == "buy" and (imbalance < self.min_imbalance or delta <= 0):
            return None
        if side == "sell" and (imbalance > -self.min_imbalance or delta >= 0):
            return None

        mid = book.mid_price
        distance = mid * self.stop_distance_bps / Decimal("10000")
        entry = book.best_bid if side == "buy" else book.best_ask
        if side == "buy":
            stop, target = entry - distance, entry + distance * self.reward_risk
        else:
            stop, target = entry + distance, entry - distance * self.reward_risk
        if min(entry, stop, target) <= 0:
            return None
        short_address = f"{address[:8]}…{address[-6:]}"
        return TradingSignal(
            symbol=book.symbol,
            side=side,
            entry=entry,
            stop_loss=stop,
            take_profit=target,
            imbalance=imbalance,
            trade_delta=delta,
            spread_bps=book.spread_bps,
            created_at_ms=now_ms,
            reason=(
                f"Top-200 whale confirmation: {short_address}, "
                f"notional {notional:,.0f} USD; OKX order-flow agrees. Paper only."
            ),
        )
