"""Deterministic scalping signal generation; no LLM call in the hot path."""

from __future__ import annotations

from decimal import Decimal

from .models import MarketTrade, OrderBookSnapshot, TradingSignal
from .orderbook import bid_ask_imbalance, liquidity_walls, trade_delta


class ScalpingEngine:
    def __init__(
        self,
        whitelist: set[str] | None = None,
        imbalance_threshold: Decimal = Decimal("0.25"),
        stop_distance_bps: Decimal = Decimal("12"),
        reward_risk: Decimal = Decimal("1.8"),
        max_spread_bps: Decimal = Decimal("8"),
        max_data_age_ms: int = 1_500,
        breakout_buffer_bps: Decimal = Decimal("2"),
    ):
        if not (Decimal("0") < imbalance_threshold < Decimal("1")):
            raise ValueError("imbalance_threshold must be between 0 and 1.")
        if stop_distance_bps <= 0 or reward_risk <= 0:
            raise ValueError("Stop distance and reward/risk must be positive.")
        if not breakout_buffer_bps.is_finite() or breakout_buffer_bps < 0:
            raise ValueError("breakout_buffer_bps must be finite and non-negative.")
        self.whitelist = set(whitelist or ())
        self.imbalance_threshold = imbalance_threshold
        self.stop_distance_bps = stop_distance_bps
        self.reward_risk = reward_risk
        self.max_spread_bps = max_spread_bps
        self.max_data_age_ms = max_data_age_ms
        self.breakout_buffer_bps = breakout_buffer_bps

    def evaluate(
        self,
        book: OrderBookSnapshot,
        trades: list[MarketTrade],
        now_ms: int,
    ) -> TradingSignal | None:
        if self.whitelist and book.symbol not in self.whitelist:
            return None
        age = now_ms - book.received_at_ms
        if age < 0 or age > self.max_data_age_ms:
            return None
        if book.spread_bps > self.max_spread_bps or not trades:
            return None
        recent = [trade for trade in trades if trade.symbol == book.symbol
                  and 0 <= now_ms - trade.timestamp_ms <= self.max_data_age_ms]
        if not recent:
            return None

        imbalance = bid_ask_imbalance(book, depth=min(10, len(book.bids), len(book.asks)))
        delta = trade_delta(recent)
        walls = liquidity_walls(book, depth=min(20, len(book.bids), len(book.asks)))
        mid = book.mid_price

        side = None
        reason = ""
        if len(recent) >= 3:
            prior_prices = [trade.price for trade in recent[:-1]]
            last_price = recent[-1].price
            buffer = self.breakout_buffer_bps / Decimal("10000")
            if (
                last_price > max(prior_prices) * (Decimal("1") + buffer)
                and delta > 0
                and imbalance >= self.imbalance_threshold
            ):
                side = "buy"
                reason = "Local trade-range breakout with positive aggressor delta and Bid imbalance."
            elif (
                last_price < min(prior_prices) * (Decimal("1") - buffer)
                and delta < 0
                and imbalance <= -self.imbalance_threshold
            ):
                side = "sell"
                reason = "Local trade-range breakdown with negative aggressor delta and Ask imbalance."

        if side is None and imbalance >= self.imbalance_threshold and delta > 0 and walls["bids"]:
            side = "buy"
            reason = "Bid-side imbalance, positive aggressor delta and visible bid liquidity wall."
        elif side is None and imbalance <= -self.imbalance_threshold and delta < 0 and walls["asks"]:
            side = "sell"
            reason = "Ask-side imbalance, negative aggressor delta and visible ask liquidity wall."
        if side is None:
            return None

        stop_fraction = self.stop_distance_bps / Decimal("10000")
        distance = mid * stop_fraction
        if side == "buy":
            entry = book.best_bid
            stop = entry - distance
            target = entry + distance * self.reward_risk
        else:
            entry = book.best_ask
            stop = entry + distance
            target = entry - distance * self.reward_risk
        if stop <= 0 or target <= 0:
            return None
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
            reason=reason,
        )
