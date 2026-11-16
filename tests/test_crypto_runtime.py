from decimal import Decimal

from crypto_analyst.engine import ScalpingEngine
from crypto_analyst.paper import PaperBroker
from crypto_analyst.risk import RiskManager
from crypto_analyst.runtime import PaperScalpingRuntime


def book_message(symbol="BTC-USDT-SWAP", ts=10_000):
    return {
        "arg": {"channel": "books5", "instId": symbol},
        "data": [{
            "ts": str(ts),
            "bids": [["100", "50000"], ["99.9", "10000"], ["99.8", "10000"]],
            "asks": [["100.05", "10000"], ["100.1", "10000"], ["100.15", "10000"]],
        }],
    }


def trade_message(symbol="BTC-USDT-SWAP", ts=10_001):
    return {
        "arg": {"channel": "trades", "instId": symbol},
        "data": [{
            "side": "buy", "px": "100.05", "sz": "5",
            "ts": str(ts), "tradeId": str(ts),
        }],
    }


def test_runtime_generates_paper_order_from_book_and_trade_flow():
    runtime = PaperScalpingRuntime(
        ScalpingEngine(whitelist={"BTC-USDT-SWAP"}),
        RiskManager(),
        PaperBroker(),
        signal_cooldown_ms=0,
    )
    assert runtime.on_market_message(book_message(), 10_000) == []
    signals = runtime.on_market_message(trade_message(), 10_001)
    assert len(signals) == 1
    assert signals[0].side == "buy"
    assert len(runtime.orders) == 1
    assert runtime.orders[0].status == "open"
    assert runtime.event_count == 2


def test_runtime_does_not_duplicate_an_active_symbol_order():
    runtime = PaperScalpingRuntime(
        ScalpingEngine(whitelist={"BTC-USDT-SWAP"}),
        RiskManager(),
        PaperBroker(),
        signal_cooldown_ms=0,
    )
    runtime.on_market_message(book_message(), 10_000)
    assert len(runtime.on_market_message(trade_message(), 10_001)) == 1
    second = book_message(ts=10_002)
    runtime.on_market_message(second, 10_002)
    assert runtime.on_market_message(trade_message(ts=10_003), 10_003) == []
    assert len(runtime.orders) == 1


def test_runtime_passes_contract_multiplier_to_paper_order():
    runtime = PaperScalpingRuntime(
        ScalpingEngine(whitelist={"BTC-USDT-SWAP"}),
        RiskManager(),
        PaperBroker(),
        signal_cooldown_ms=0,
        contract_multipliers={"BTC-USDT-SWAP": Decimal("0.01")},
        derivative_symbols={"BTC-USDT-SWAP"},
    )
    runtime.on_market_message(book_message(), 10_000)
    assert runtime.on_market_message(trade_message(), 10_001)
    assert runtime.orders[0].contract_multiplier == Decimal("0.01")
