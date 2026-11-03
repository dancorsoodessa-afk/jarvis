from agent.crypto.analysis import analyze
from agent.crypto.market import MarketSnapshot, PublicMarketClient
from agent.crypto.risk import build_plan


def _snapshot(closes):
    candles = []
    for index, close in enumerate(closes):
        candles.append((index * 3600000, close - 0.5, close + 1, close - 1, close, 100.0))
    return MarketSnapshot(
        "BTCUSDT", "TEST", closes[-1], 0.0, 1000000.0,
        tuple(candles), 1.0, "test fixture",
    )


def test_market_symbol_normalization():
    assert PublicMarketClient._symbol("btc") == "BTCUSDT"
    assert PublicMarketClient._symbol("ethusdt") == "ETHUSDT"


def test_analysis_returns_hold_for_flat_market():
    report = analyze(_snapshot([100.0] * 80))
    assert report.direction == "HOLD"
    assert report.confidence == 0
    assert report.rsi14 == 50.0


def test_risk_plan_long_has_correct_order_and_bounded_risk():
    plan = build_plan("LONG", 100.0, 2.0, 1000.0, 1.0, 2.0, 1.0)
    assert plan.stop_loss < plan.entry < plan.take_profit_1 < plan.take_profit_2
    assert plan.risk_amount <= 10.0 + 1e-9
    assert plan.position_value <= 1000.0 + 1e-9


def test_risk_plan_short_has_correct_order():
    plan = build_plan("SHORT", 100.0, 2.0, 1000.0, 1.0, 2.0, 1.0)
    assert plan.take_profit_2 < plan.take_profit_1 < plan.entry < plan.stop_loss


def test_risk_rejects_more_than_two_percent():
    try:
        build_plan("LONG", 100.0, 2.0, 1000.0, 2.1)
    except ValueError as exc:
        assert "2%" in str(exc)
    else:
        raise AssertionError("Risk above 2% must be rejected")


def test_fetch_all_returns_each_available_exchange(monkeypatch):
    client = PublicMarketClient()
    snapshot = _snapshot([100.0] * 80)
    monkeypatch.setattr(client, "_binance", lambda *args: snapshot)
    monkeypatch.setattr(client, "_bybit", lambda *args: MarketSnapshot(
        "BTCUSDT", "Bybit", 100.1, 0.1, 200000.0, snapshot.candles, 1.0, "mock"
    ))
    monkeypatch.setattr(client, "_okx", lambda *args: MarketSnapshot(
        "BTCUSDT", "OKX", 99.9, -0.1, 300000.0, snapshot.candles, 1.0, "mock"
    ))
    result = client.fetch_all("BTCUSDT", "1h")
    assert [item.exchange for item in result] == ["Binance", "Bybit", "OKX"]
