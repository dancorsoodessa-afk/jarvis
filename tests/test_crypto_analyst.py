from agent.crypto.analyst import build_signal, calculate_indicators


def test_build_signal_long_has_entry_stop_target_and_risk():
    signal = build_signal(
        "BTC-USDT", 100.0,
        {"ema_fast": 102.0, "ema_slow": 100.0, "rsi": 58.0, "macd": 1.2, "atr": 2.0},
    )
    assert signal["side"] == "LONG"
    assert signal["entry"] == 100.0
    assert signal["stop_loss"] < signal["entry"] < signal["take_profit"]
    assert signal["risk_reward"] >= 1.9
    assert signal["risk_percent"] == 1.0


def test_build_signal_short_reverses_stop_and_target():
    signal = build_signal(
        "ETH-USDT", 200.0,
        {"ema_fast": 98.0, "ema_slow": 100.0, "rsi": 42.0, "macd": -1.0, "atr": 3.0},
    )
    assert signal["side"] == "SHORT"
    assert signal["take_profit"] < signal["entry"] < signal["stop_loss"]


def test_build_signal_rejects_mixed_conditions():
    assert build_signal(
        "BTC-USDT", 100.0,
        {"ema_fast": 102.0, "ema_slow": 100.0, "rsi": 48.0, "macd": 1.0, "atr": 2.0},
    ) is None


def test_calculate_indicators_returns_expected_keys():
    candles = [
        {"open": float(i), "high": float(i) + 1, "low": float(i) - 1, "close": float(i), "volume": 10.0}
        for i in range(1, 40)
    ]
    result = calculate_indicators(candles)
    assert {"ema_fast", "ema_slow", "rsi", "macd", "atr"} <= result.keys()
    assert result["ema_fast"] > result["ema_slow"]
