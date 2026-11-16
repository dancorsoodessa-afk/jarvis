"""Event-driven paper scalping runtime."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .engine import ScalpingEngine
from .market_state import MarketState
from .models import MarketTrade, TradingSignal
from .paper import PaperBroker, PaperOrder
from .risk import RiskManager


class PaperScalpingRuntime:
    """Connect normalized public market events to signal, risk, and paper layers."""

    def __init__(
        self,
        engine: ScalpingEngine,
        risk_manager: RiskManager,
        broker: PaperBroker,
        market_state: MarketState | None = None,
        equity: Decimal | None = None,
        signal_cooldown_ms: int = 3_000,
    ):
        if signal_cooldown_ms < 0:
            raise ValueError("signal_cooldown_ms cannot be negative.")
        self.engine = engine
        self.risk_manager = risk_manager
        self.broker = broker
        self.state = market_state or MarketState()
        self.fixed_equity = equity
        self.signal_cooldown_ms = signal_cooldown_ms
        self.last_signal_at: dict[str, int] = {}
        self.signals: list[TradingSignal] = []
        self.orders: list[PaperOrder] = []
        self.event_count = 0

    def _active_exposure_count(self) -> int:
        exposed_symbols = {
            position.symbol for position in self.broker.positions.values()
            if position.status == "open"
        }
        exposed_symbols.update(
            order.symbol for order in self.broker.orders.values()
            if order.status in {"open", "partially_filled"}
        )
        return len(exposed_symbols)

    def on_market_message(
        self,
        message: dict[str, Any],
        received_at_ms: int,
    ) -> list[TradingSignal]:
        self.event_count += 1
        self.state.on_okx_message(message, received_at_ms)
        arg = message.get("arg") or {}
        symbol = str(arg.get("instId") or "")
        channel = arg.get("channel")

        if channel == "trades":
            for row in message.get("data") or []:
                try:
                    trade = MarketTrade.from_okx(symbol, row)
                except (KeyError, TypeError, ValueError):
                    continue
                self.broker.on_trade(trade)

        book = self.state.orderbooks.get(symbol)
        if book is None:
            return []
        recent = self.state.recent_trades(
            symbol,
            since_ms=max(0, received_at_ms - self.engine.max_data_age_ms),
        )
        signal = self.engine.evaluate(book, recent, received_at_ms)
        if signal is None:
            return []

        last = self.last_signal_at.get(symbol, 0)
        if received_at_ms - last < self.signal_cooldown_ms:
            return []
        if self.broker.has_active_order_or_position(symbol):
            return []

        decision = self.risk_manager.approve(
            signal=signal,
            equity=self.fixed_equity or self.broker.cash,
            daily_pnl=self.broker.realized_pnl,
            open_positions=self._active_exposure_count(),
            now_ms=received_at_ms,
            data_timestamp_ms=book.received_at_ms,
        )
        if not decision.approved:
            return []

        self.broker.place_limit(signal, decision.quantity)
        self.signals.append(signal)
        latest_order_id = next(reversed(self.broker.orders))
        self.orders.append(self.broker.orders[latest_order_id])
        self.last_signal_at[symbol] = received_at_ms
        return [signal]
