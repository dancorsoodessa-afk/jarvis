from decimal import Decimal

from crypto_analyst.engine import ScalpingEngine
from crypto_analyst.models import MarketTrade
from crypto_analyst.paper import PaperBroker
from crypto_analyst.risk import RiskManager
from crypto_analyst.runtime import PaperScalpingRuntime
from crypto_analyst.whale_intel import WhaleTrade


def test_confirmed_whale_fill_creates_paper_order_only():
    now = 1_700_000_000_000
    runtime = PaperScalpingRuntime(
        ScalpingEngine(whitelist={"BTC-USDT-SWAP"}),
        RiskManager(),
        PaperBroker(Decimal("10000")),
        signal_cooldown_ms=0,
    )
    runtime.state.on_okx_message({
        "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "ts": str(now), "bids": [["100", "500"], ["99.9", "10"]],
            "asks": [["100.05", "10"], ["100.1", "10"]],
        }],
    }, now)
    for index, amount in enumerate(("2", "3")):
        runtime.state.on_okx_message({
            "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
            "data": [{
                "side": "buy", "px": "100.05", "sz": amount,
                "ts": str(now - 100 + index * 50), "tradeId": str(index),
            }],
        }, now)
    wallet = "0x" + "a" * 40
    event = WhaleTrade(
        timestamp=str(now - 100), address=wallet, coin="BTC", side="buy",
        price=Decimal("100"), size_usd=Decimal("500000"),
        venue="Nansen", raw={},
    )
    signals = runtime.on_whale_trade(event, {wallet}, now)
    assert len(signals) == 1
    assert len(runtime.orders) == 1
    assert runtime.orders[0].status == "open"
    assert runtime.broker.live_execution_enabled is False
    assert not hasattr(runtime.broker, "create_exchange_order")


def test_whale_copy_runtime_does_not_duplicate_active_symbol_order():
    now = 1_700_000_000_000
    runtime = PaperScalpingRuntime(
        ScalpingEngine(whitelist={"BTC-USDT-SWAP"}),
        RiskManager(),
        PaperBroker(Decimal("10000")),
        signal_cooldown_ms=0,
    )
    runtime.state.on_okx_message({
        "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
        "data": [{"ts": str(now), "bids": [["100", "500"]], "asks": [["100.05", "10"]]}],
    }, now)
    for index in range(2):
        runtime.state.on_okx_message({
            "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
            "data": [{"side": "buy", "px": "100.05", "sz": "2", "ts": str(now - 100 + index * 50)}],
        }, now)
    wallet = "0x" + "b" * 40
    event = WhaleTrade(str(now - 100), wallet, "BTC", "buy", Decimal("100"), Decimal("500000"), "Nansen", {})
    assert runtime.on_whale_trade(event, {wallet}, now)
    assert runtime.on_whale_trade(event, {wallet}, now + 1) == []
    assert len(runtime.orders) == 1
