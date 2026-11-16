from decimal import Decimal

from crypto_analyst.engine import ScalpingEngine
from crypto_analyst.models import Level, MarketTrade, OrderBookSnapshot
from crypto_analyst.orderbook import cumulative_volume_delta, large_trades, probable_iceberg


def test_cvd_and_large_trade_detection():
    trades = [
        MarketTrade("BTC-USDT", "buy", Decimal("100"), Decimal("2"), 1),
        MarketTrade("BTC-USDT", "sell", Decimal("101"), Decimal("1"), 2),
        MarketTrade("BTC-USDT", "buy", Decimal("102"), Decimal("3"), 3),
    ]
    assert cumulative_volume_delta(trades) == (Decimal("2"), Decimal("1"), Decimal("4"))
    assert large_trades(trades, Decimal("200")) == [trades[0], trades[2]]


def test_probable_iceberg_requires_repeated_smaller_prints():
    repeated = [
        MarketTrade("BTC-USDT", "buy", Decimal("100"), Decimal("2"), 1),
        MarketTrade("BTC-USDT", "buy", Decimal("100"), Decimal("2"), 2),
        MarketTrade("BTC-USDT", "buy", Decimal("100"), Decimal("2"), 3),
    ]
    single = [MarketTrade("BTC-USDT", "buy", Decimal("100"), Decimal("10"), 1)]
    assert probable_iceberg(repeated, Decimal("5"))
    assert not probable_iceberg(single, Decimal("5"))


def test_scalping_engine_detects_local_trade_range_breakout():
    book = OrderBookSnapshot(
        "BTC-USDT",
        (Level(Decimal("100"), Decimal("1000")), Level(Decimal("99.99"), Decimal("100")),
         Level(Decimal("99.98"), Decimal("100"))),
        (Level(Decimal("100.05"), Decimal("100")), Level(Decimal("100.06"), Decimal("100")),
         Level(Decimal("100.07"), Decimal("100"))),
        1000, 1000,
    )
    trades = [
        MarketTrade("BTC-USDT", "buy", Decimal("100.01"), Decimal("2"), 1000),
        MarketTrade("BTC-USDT", "buy", Decimal("100.02"), Decimal("2"), 1001),
        MarketTrade("BTC-USDT", "buy", Decimal("100.05"), Decimal("2"), 1002),
    ]
    signal = ScalpingEngine(whitelist={"BTC-USDT"}).evaluate(book, trades, 1002)
    assert signal is not None and signal.side == "buy"
    assert "breakout" in signal.reason.lower()
