from decimal import Decimal

from crypto_analyst.engine import ScalpingEngine
from crypto_analyst.models import Level, OrderBookSnapshot
from crypto_analyst.paper import PaperBroker
from crypto_analyst.risk import RiskManager
from crypto_analyst.runtime import PaperScalpingRuntime


def make_book():
    return OrderBookSnapshot(
        symbol="BTC-USDT-SWAP",
        bids=(
            Level(Decimal("100"), Decimal("100")),
            Level(Decimal("99.9"), Decimal("10")),
            Level(Decimal("99.8"), Decimal("10")),
        ),
        asks=(
            Level(Decimal("100.05"), Decimal("10")),
            Level(Decimal("100.1"), Decimal("10")),
            Level(Decimal("100.15"), Decimal("10")),
        ),
        timestamp_ms=10_000,
        received_at_ms=10_000,
    )


def test_runtime_creates_only_paper_order_after_book_and_trade_confirmation():
    runtime = PaperScalpingRuntime(
        ScalpingEngine(whitelist={"BTC-USDT-SWAP"}),
        RiskManager(),
        PaperBroker(),
        signal_cooldown_ms=0,
    )
    runtime.on_market_message({
        "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "ts": "10000",
            "bids": [["100", "100"], ["99.9", "10"], ["99.8", "10"]],
            "asks": [["100.05", "10"], ["100.1", "10"], ["100.15", "10"]],
        }],
    }, 10_000)

    signals = runtime.on_market_message({
        "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "side": "buy", "px": "100.05", "sz": "5",
            "ts": "10001", "tradeId": "1",
        }],
    }, 10_001)

    assert len(signals) == 1
    assert len(runtime.orders) == 1
    assert runtime.orders[0].status == "open"
    assert runtime.broker.live_execution_enabled is False


def test_runtime_does_not_duplicate_active_order_for_same_symbol():
    runtime = PaperScalpingRuntime(
        ScalpingEngine(whitelist={"BTC-USDT-SWAP"}),
        RiskManager(),
        PaperBroker(),
        signal_cooldown_ms=0,
    )
    book_message = {
        "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "ts": "10000",
            "bids": [["100", "100"], ["99.9", "10"], ["99.8", "10"]],
            "asks": [["100.05", "10"], ["100.1", "10"], ["100.15", "10"]],
        }],
    }
    runtime.on_market_message(book_message, 10_000)
    trade_message = {
        "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "side": "buy", "px": "100.05", "sz": "5",
            "ts": "10001", "tradeId": "1",
        }],
    }
    assert len(runtime.on_market_message(trade_message, 10_001)) == 1
    assert runtime.on_market_message(book_message, 10_002) == []
    assert len(runtime.orders) == 1
