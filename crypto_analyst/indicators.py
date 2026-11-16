"""Deterministic technical-indicator primitives."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence


def _series(values: Sequence[float], name: str = "values") -> list[float]:
    result = [float(value) for value in values]
    if any(not isfinite(value) for value in result):
        raise ValueError(f"{name} must contain only finite numbers.")
    return result


def _period(period: int) -> None:
    if period < 1:
        raise ValueError("period must be positive.")


def ema(values: Sequence[float], period: int) -> list[float]:
    _period(period)
    data = _series(values)
    if not data:
        return []
    alpha = 2.0 / (period + 1.0)
    current = data[0]
    result = []
    for value in data:
        current = alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    _period(period)
    data = _series(values)
    result: list[float | None] = [None] * len(data)
    if len(data) <= period:
        return result
    changes = [data[index] - data[index - 1] for index in range(1, len(data))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + gain / loss)

    result[period] = value(avg_gain, avg_loss)
    for index in range(period + 1, len(data)):
        offset = index - 1
        avg_gain = ((avg_gain * (period - 1)) + gains[offset]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[offset]) / period
        result[index] = value(avg_gain, avg_loss)
    return result


@dataclass(frozen=True)
class MACDResult:
    line: tuple[float, ...]
    signal: tuple[float, ...]
    histogram: tuple[float, ...]


def macd(values: Sequence[float], fast_period: int = 12,
         slow_period: int = 26, signal_period: int = 9) -> MACDResult:
    _period(fast_period)
    _period(slow_period)
    _period(signal_period)
    if fast_period >= slow_period:
        raise ValueError("fast_period must be smaller than slow_period.")
    data = _series(values)
    line = [a - b for a, b in zip(ema(data, fast_period), ema(data, slow_period))]
    signal = ema(line, signal_period)
    return MACDResult(tuple(line), tuple(signal), tuple(a - b for a, b in zip(line, signal)))


def vwap(prices: Sequence[float], volumes: Sequence[float]) -> list[float | None]:
    price_data = _series(prices, "prices")
    volume_data = _series(volumes, "volumes")
    if len(price_data) != len(volume_data):
        raise ValueError("prices and volumes must have equal length.")
    if any(volume < 0 for volume in volume_data):
        raise ValueError("volumes cannot be negative.")
    total_value = total_volume = 0.0
    result = []
    for price, volume in zip(price_data, volume_data):
        total_value += price * volume
        total_volume += volume
        result.append(total_value / total_volume if total_volume else None)
    return result


def bollinger_bands(values: Sequence[float], period: int = 20,
                    deviations: float = 2.0) -> list[tuple[float, float, float] | None]:
    _period(period)
    if deviations <= 0 or not isfinite(deviations):
        raise ValueError("deviations must be positive and finite.")
    data = _series(values)
    result: list[tuple[float, float, float] | None] = [None] * len(data)
    for index in range(period - 1, len(data)):
        window = data[index - period + 1:index + 1]
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / period
        width = sqrt(variance) * deviations
        result[index] = (mean + width, mean, mean - width)
    return result


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
        period: int = 14) -> list[float | None]:
    _period(period)
    high_data, low_data, close_data = (
        _series(highs, "highs"), _series(lows, "lows"), _series(closes, "closes")
    )
    if not (len(high_data) == len(low_data) == len(close_data)):
        raise ValueError("highs, lows, and closes must have equal length.")
    if any(high < low for high, low in zip(high_data, low_data)):
        raise ValueError("Each high must be >= its low.")
    ranges = []
    for index, (high, low) in enumerate(zip(high_data, low_data)):
        if index == 0:
            ranges.append(high - low)
        else:
            previous = close_data[index - 1]
            ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    result: list[float | None] = [None] * len(ranges)
    if len(ranges) < period:
        return result
    current = sum(ranges[:period]) / period
    result[period - 1] = current
    for index in range(period, len(ranges)):
        current = ((current * (period - 1)) + ranges[index]) / period
        result[index] = current
    return result
