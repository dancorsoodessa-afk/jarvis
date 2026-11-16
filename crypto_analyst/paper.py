"""Paper-only broker with trade-driven fills and virtual SL/TP."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from .models import MarketTrade, TradingSignal
from .trailing_stop import TrailingStopManager


@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    contract_multiplier: Decimal = Decimal("1")
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal = Decimal("0")
    fee_paid: Decimal = Decimal("0")
    status: str = "open"


@dataclass
class PaperPosition:
    position_id: str
    order_id: str
    symbol: str
    side: str
    entry_price: Decimal
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    contract_multiplier: Decimal
    entry_fee: Decimal
    favorable_price: Decimal | None = None
    status: str = "open"
    exit_price: Decimal | None = None
    exit_fee: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


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

    def __init__(
        self,
        starting_balance: Decimal = Decimal("10000"),
        maker_fee_rate: Decimal = Decimal("0.0002"),
        trailing_stop_bps: Decimal = Decimal("30"),
    ):
        if not starting_balance.is_finite() or starting_balance <= 0:
            raise ValueError("starting_balance must be positive and finite.")
        if not maker_fee_rate.is_finite() or maker_fee_rate < 0:
            raise ValueError("maker_fee_rate cannot be negative.")
        self.initial_balance = starting_balance
        self.cash = starting_balance
        self.maker_fee_rate = maker_fee_rate
        self.trailing_stop_manager = TrailingStopManager(trailing_stop_bps)
        self.orders: dict[str, PaperOrder] = {}
        self.positions: dict[str, PaperPosition] = {}
        self.fills: list[PaperFill] = []
        self.realized_pnl = Decimal("0")
        self.live_execution_enabled = False

    def place_limit(
        self,
        signal: TradingSignal,
        quantity: Decimal,
        contract_multiplier: Decimal = Decimal("1"),
    ) -> PaperOrder:
        if self.live_execution_enabled:
            raise RuntimeError("Live execution is permanently disabled in PaperBroker.")
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("quantity must be positive and finite.")
        if not contract_multiplier.is_finite() or contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be positive.")
        order = PaperOrder(
            order_id=uuid4().hex,
            symbol=signal.symbol,
            side=signal.side,
            price=signal.entry,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            contract_multiplier=contract_multiplier,
        )
        self.orders[order.order_id] = order
        return order

    def cancel(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if order is None or order.status not in {"open", "partially_filled"}:
            return False
        order.status = "cancelled"
        return True

    def _update_positions(self, trade: MarketTrade) -> None:
        for position in self.positions.values():
            if position.status != "open" or position.symbol != trade.symbol:
                continue
            if position.side == "buy":
                stop_hit = trade.price <= position.stop_loss
                target_hit = trade.price >= position.take_profit
            else:
                stop_hit = trade.price >= position.stop_loss
                target_hit = trade.price <= position.take_profit
            if not (stop_hit or target_hit):
                continue

            exit_price = trade.price
            gross = (
                (exit_price - position.entry_price) * position.quantity
                if position.side == "buy"
                else (position.entry_price - exit_price) * position.quantity
            ) * position.contract_multiplier
            exit_fee = exit_price * position.quantity * position.contract_multiplier * self.maker_fee_rate
            position.exit_price = exit_price
            position.exit_fee = exit_fee
            position.realized_pnl = gross - position.entry_fee - exit_fee
            position.status = "closed"
            self.cash += gross - exit_fee
            self.realized_pnl += gross - position.entry_fee - exit_fee

    def on_trade(self, trade: MarketTrade) -> list[PaperFill]:
        if self.live_execution_enabled:
            raise RuntimeError("Live execution is permanently disabled in PaperBroker.")
        self._update_positions(trade)
        for position in self.positions.values():
            if position.status == "open" and position.symbol == trade.symbol:
                self.trailing_stop_manager.update(position, trade.price)
        new_fills = []
        available_amount = trade.amount
        for order in self.orders.values():
            if available_amount <= 0:
                break
            if order.status not in {"open", "partially_filled"} or order.symbol != trade.symbol:
                continue
            executable = (
                (order.side == "buy" and trade.side == "sell" and trade.price <= order.price)
                or (order.side == "sell" and trade.side == "buy" and trade.price >= order.price)
            )
            if not executable:
                continue
            remaining = order.quantity - order.filled_quantity
            filled = min(remaining, available_amount)
            if filled <= 0:
                continue
            available_amount -= filled
            fee = filled * order.price * order.contract_multiplier * self.maker_fee_rate
            previous_value = order.average_fill_price * order.filled_quantity
            order.filled_quantity += filled
            order.average_fill_price = (previous_value + order.price * filled) / order.filled_quantity
            order.fee_paid += fee
            order.status = "filled" if order.filled_quantity >= order.quantity else "partially_filled"
            self.cash -= fee
            position = PaperPosition(
                position_id=uuid4().hex,
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                entry_price=order.price,
                quantity=filled,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                contract_multiplier=order.contract_multiplier,
                entry_fee=fee,
                favorable_price=order.price,
            )
            self.positions[position.position_id] = position
            fill = PaperFill(order.order_id, order.symbol, order.side, order.price, filled, fee)
            self.fills.append(fill)
            new_fills.append(fill)
        return new_fills

    def open_position_count(self) -> int:
        return sum(position.status == "open" for position in self.positions.values())

    def has_active_order_or_position(self, symbol: str) -> bool:
        active_order = any(
            order.symbol == symbol and order.status in {"open", "partially_filled"}
            for order in self.orders.values()
        )
        active_position = any(
            position.symbol == symbol and position.status == "open"
            for position in self.positions.values()
        )
        return active_order or active_position
