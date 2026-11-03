"""Transparent indicator calculations and conservative signal classification."""
from __future__ import annotations

from dataclasses import dataclass
from .market import MarketSnapshot


@dataclass(frozen=True)
class TechnicalReport:
    direction: str
    confidence: int
    price: float
    ema9: float
    ema21: float
    ema50: float
    rsi14: float
    atr14: float
    support: float
    resistance: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def _ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"Недостаточно свечей для EMA{period}")
    alpha = 2.0 / (period + 1.0)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = value * alpha + result * (1.0 - alpha)
    return result


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError("Недостаточно свечей для RSI")
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def analyze(snapshot: MarketSnapshot) -> TechnicalReport:
    candles = snapshot.candles
    closes = [c[4] for c in candles]
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    if len(closes) < 55:
        raise ValueError("Для анализа требуется минимум 55 свечей")
    ema9, ema21, ema50 = _ema(closes, 9), _ema(closes, 21), _ema(closes, 50)
    rsi = _rsi(closes)
    true_ranges = []
    for i in range(1, len(candles)):
        true_ranges.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    atr = sum(true_ranges[-14:]) / 14
    support = min(lows[-30:])
    resistance = max(highs[-30:])
    score = 0
    reasons = []
    if ema9 > ema21 > ema50:
        score += 2
        reasons.append("EMA9 > EMA21 > EMA50: восходящая структура")
    elif ema9 < ema21 < ema50:
        score -= 2
        reasons.append("EMA9 < EMA21 < EMA50: нисходящая структура")
    else:
        reasons.append("EMA не подтверждают единое направление")
    if snapshot.price > ema21:
        score += 1
        reasons.append("Цена выше EMA21")
    elif snapshot.price < ema21:
        score -= 1
        reasons.append("Цена ниже EMA21")
    if 50 <= rsi <= 68:
        score += 1
        reasons.append("RSI поддерживает бычий импульс без сильной перекупленности")
    elif 32 <= rsi < 50:
        score -= 1
        reasons.append("RSI поддерживает медвежий импульс без сильной перепроданности")
    elif rsi > 75:
        reasons.append("RSI показывает перекупленность — вход в LONG рискован")
    elif rsi < 25:
        reasons.append("RSI показывает перепроданность — вход в SHORT рискован")
    warnings = []
    if atr <= 0 or snapshot.price <= 0:
        raise ValueError("Некорректная волатильность или цена")
    if snapshot.price < support or snapshot.price > resistance:
        warnings.append("Цена вышла за локальный диапазон; проверьте свежесть свечей")
    if abs(score) < 3:
        direction, confidence = "HOLD", 0
        warnings.append("Недостаточно согласованных факторов для торгового сигнала")
    else:
        direction = "LONG" if score > 0 else "SHORT"
        confidence = min(85, 50 + abs(score) * 8)
    if rsi >= 70 and direction == "LONG":
        direction, confidence = "HOLD", 0
        warnings.append("Сигнал LONG отменён из-за перекупленности RSI")
    if rsi <= 30 and direction == "SHORT":
        direction, confidence = "HOLD", 0
        warnings.append("Сигнал SHORT отменён из-за перепроданности RSI")
    return TechnicalReport(
        direction, confidence, snapshot.price, ema9, ema21, ema50, rsi, atr,
        support, resistance, tuple(reasons), tuple(warnings),
    )
