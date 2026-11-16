import pytest

from crypto_analyst.indicators import atr, bollinger_bands, ema, macd, rsi, vwap


def test_ema_returns_aligned_series():
    values = ema([1, 2, 3, 4], 2)
    assert len(values) == 4 and values[-1] > values[0]


def test_rsi_is_bounded_and_detects_monotonic_gain():
    values = rsi([1, 2, 3, 4, 5, 6], period=3)
    assert values[2] is None
    assert values[-1] == 100.0


def test_macd_and_bollinger_shapes():
    result = macd(list(range(1, 40)), fast_period=3, slow_period=6, signal_period=3)
    assert len(result.line) == 39
    bands = bollinger_bands(list(range(1, 25)), period=5)
    assert bands[3] is None and bands[-1][0] > bands[-1][1] > bands[-1][2]


def test_vwap_and_atr():
    assert vwap([10, 20], [1, 3]) == [10.0, 17.5]
    values = atr([11, 12, 13], [9, 10, 11], [10, 11, 12], period=2)
    assert values[0] is None and values[1] is not None


def test_indicator_rejects_bad_input():
    with pytest.raises(ValueError):
        ema([1, float("nan")], 2)
    with pytest.raises(ValueError):
        vwap([1, 2], [1])
