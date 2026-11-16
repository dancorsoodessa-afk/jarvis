"""Paper-only broker. This module has no exchange order API or credentials."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from .models import MarketTrade, TradingSignal


@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal = Decimal("0")
    fee_paid: Decimal = Decimal("0")
    status: str = "open"


@dataclass(frozen=True)
class PaperFill:
    order_id: str
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    fee: Decimal


class PaperBroker:
    """Conservative maker-style simulation driven by public trade prints."""

    def __init__(self, starting_balance: Decimal = Decimal("10000"),
                 maker_fee_rate: Decimal = Decimal("0.0002")):
        if starting_balance <= 0:
            raise ValueError("starting_balance must be positive.")
        if maker_fee_rate < 0:
            raise ValueError("maker_fee_rate cannot be negative.")
        self.initial_balance = starting_balance
        self.cash = starting_balance
        self.maker_fee_rate = maker_fee_rate
        self.orders: dict[str, PaperOrder] = {}
        self.fills: list[PaperFill] = []
        self.live_execution_enabled = False

    def place_limit(self, signal: TradingSignal, quantity: Decimal) -> PaperOrder:
        if self.live_execution_enabled:
            raise RuntimeError("Live execution is permanently disabled in PaperBroker.")
        if quantity <= 0:
            raise ValueError("quantity must be positive.")
        order = PaperOrder(
            order_id=uuid4().hex,
            symbol=signal.symbol,
            side=signal.side,
            price=signal.entry,
            quantity=quantity,
        )
        self.orders[order.order_id] = order
        return order

    def cancel(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if order is None or order.status != "open":
            return False
        order.status = "cancelled"
        return True

    def on_trade(self, trade: MarketTrade) -> list[PaperFill]:
        if self.live_execution_enabled:
            raise RuntimeError("Live execution is permanently disabled in PaperBroker.")
        new_fills = []
        for order in self.orders.values():
            if order.status != "open" or order.symbol != trade.symbol:
                continue
            # A sell aggressor consumes bids; a buy aggressor consumes asks.
            executable = (
                (order.side == "buy" and trade.side == "sell" and trade.price <= order.price)
                or (order.side == "sell" and trade.side == "buy" and trade.price >= order.price)
            )
            if not executable:
                continue
            remaining = order.quantity - order.filled_quantity
            filled = min(remaining, trade.amount)
            if filled <= 0:
                continue
            fee = filled * order.price * self.maker_fee_rate
            previous_value = order.average_fill_price * order.filled_quantity
            order.filled_quantity += filled
            order.average_fill_price = (previous_value + order.price * filled) / order.filled_quantity
            order.fee_paid += fee
            order.status = "filled" if order.filled_quantity >= order.quantity else "partially_filled"
            self.cash -= fee
            fill = PaperFill(order.order_id, order.symbol, order.side, order.price, filled, fee)
            self.fills.append(fill)
            new_fills.append(fill)
        return new_fills
