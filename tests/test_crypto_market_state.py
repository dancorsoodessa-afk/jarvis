from decimal import Decimal

from crypto_analyst.market_state import MarketState


def test_market_state_normalizes_okx_orderbook_and_trades():
    state = MarketState()
    state.on_okx_message({
        "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "ts": "1700000000000",
            "bids": [["100", "3", "0", "1"]],
            "asks": [["101", "4", "0", "1"]],
        }],
    }, received_at_ms=1_700_000_000_010)

    state.on_okx_message({
        "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "side": "buy", "px": "100.5", "sz": "2",
            "ts": "1700000000001", "tradeId": "42",
        }],
    }, received_at_ms=1_700_000_000_011)

    book = state.orderbooks["BTC-USDT-SWAP"]
    trades = state.recent_trades("BTC-USDT-SWAP")

    assert book.best_bid == Decimal("100")
    assert book.best_ask == Decimal("101")
    assert len(trades) == 1
    assert trades[0].amount == Decimal("2")
    assert trades[0].trade_id == "42"


def test_invalid_orderbook_does_not_replace_last_valid_snapshot():
    state = MarketState()
    state.on_okx_message({
        "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "ts": "1700000000000",
            "bids": [["100", "3"]],
            "asks": [["101", "4"]],
        }],
    }, received_at_ms=1_700_000_000_010)
    original = state.orderbooks["BTC-USDT-SWAP"]

    state.on_okx_message({
        "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
        "data": [{
            "ts": "1700000000002",
            "bids": [["102", "3"]],
            "asks": [["101", "4"]],
        }],
    }, received_at_ms=1_700_000_000_012)

    assert state.orderbooks["BTC-USDT-SWAP"] is original


def test_ticker_channel_is_stored():
    state = MarketState()
    state.on_okx_message({
        "arg": {"channel": "tickers", "instId": "BTC-USDT"},
        "data": [{
            "last": "100.5", "bidPx": "100", "askPx": "101",
            "ts": "1700000000000",
        }],
    }, received_at_ms=1_700_000_000_010)
    assert state.tickers["BTC-USDT"].last == "100.5"
