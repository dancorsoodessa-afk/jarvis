"""Smart-money market-structure primitives: FVG, BOS, and CHoCH."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class Candle:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume)
        if self.timestamp_ms <= 0 or any(not isfinite(value) for value in values):
            raise ValueError("Candle values and timestamp must be finite and valid.")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("Candle high/low do not contain open and close.")
        if self.low > self.high or self.volume < 0:
            raise ValueError("Candle range or volume is invalid.")


@dataclass(frozen=True)
class FairValueGap:
    direction: str
    lower: float
    upper: float
    formed_at_ms: int


@dataclass(frozen=True)
class StructureBreak:
    direction: str
    kind: str
    level: float
    timestamp_ms: int


def detect_fair_value_gaps(candles: Sequence[Candle], min_gap_bps: float = 0.0) -> list[FairValueGap]:
    if min_gap_bps < 0 or not isfinite(min_gap_bps):
        raise ValueError("min_gap_bps must be finite and non-negative.")
    result = []
    for index in range(2, len(candles)):
        left, current = candles[index - 2], candles[index]
        if left.high < current.low:
            lower, upper, direction = left.high, current.low, "bullish"
        elif left.low > current.high:
            lower, upper, direction = current.high, left.low, "bearish"
        else:
            continue
        midpoint = (lower + upper) / 2
        gap_bps = (upper - lower) / midpoint * 10_000 if midpoint else 0
        if gap_bps >= min_gap_bps:
            result.append(FairValueGap(direction, lower, upper, current.timestamp_ms))
    return result


def detect_structure_breaks(candles: Sequence[Candle], swing_window: int = 2) -> list[StructureBreak]:
    """Confirm pivots only after swing_window later bars have arrived."""
    if swing_window < 1:
        raise ValueError("swing_window must be positive.")
    last_high = last_low = None
    trend = 0
    result = []
    for index, candle in enumerate(candles):
        pivot_index = index - swing_window
        if pivot_index >= swing_window:
            pivot = candles[pivot_index]
            left = candles[pivot_index - swing_window:pivot_index]
            right = candles[pivot_index + 1:index + 1]
            if left and right:
                if pivot.high > max(item.high for item in left + right):
                    last_high = pivot.high
                if pivot.low < min(item.low for item in left + right):
                    last_low = pivot.low
        if index == 0:
            continue
        previous_close = candles[index - 1].close
        if last_high is not None and previous_close <= last_high < candle.close:
            result.append(StructureBreak("bullish", "CHoCH" if trend < 0 else "BOS",
                                         last_high, candle.timestamp_ms))
            trend = 1
        elif last_low is not None and previous_close >= last_low > candle.close:
            result.append(StructureBreak("bearish", "CHoCH" if trend > 0 else "BOS",
                                         last_low, candle.timestamp_ms))
            trend = -1
    return result
