"""Position sizing and trade-plan calculations; no order execution."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradePlan:
    direction: str
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    quantity: float
    position_value: float
    risk_amount: float
    reward_risk_1: float
    leverage_cap: float


def build_plan(direction: str, entry: float, atr: float, capital: float,
               risk_pct: float = 1.0, reward_risk: float = 2.0,
               max_leverage: float = 1.0) -> TradePlan:
    side = direction.upper()
    if side not in {"LONG", "SHORT"}:
        raise ValueError("План можно рассчитать только для LONG или SHORT")
    entry, atr, capital = float(entry), float(atr), float(capital)
    risk_pct, reward_risk, max_leverage = float(risk_pct), float(reward_risk), float(max_leverage)
    if min(entry, atr, capital, risk_pct, reward_risk, max_leverage) <= 0:
        raise ValueError("Все параметры должны быть положительными")
    if risk_pct > 2.0:
        raise ValueError("Для защиты капитала риск на сделку ограничен 2%")
    if max_leverage > 3.0:
        raise ValueError("В консервативном режиме плечо ограничено 3x")
    stop_distance = max(atr * 1.5, entry * 0.002)
    risk_amount = capital * risk_pct / 100.0
    quantity = risk_amount / stop_distance
    max_position_value = capital * max_leverage
    quantity = min(quantity, max_position_value / entry)
    position_value = quantity * entry
    actual_risk = quantity * stop_distance
    if side == "LONG":
        stop = entry - stop_distance
        tp1 = entry + stop_distance * reward_risk
        tp2 = entry + stop_distance * reward_risk * 1.5
    else:
        stop = entry + stop_distance
        tp1 = entry - stop_distance * reward_risk
        tp2 = entry - stop_distance * reward_risk * 1.5
    return TradePlan(side, entry, stop, tp1, tp2, quantity, position_value,
                     actual_risk, reward_risk, max_leverage)
