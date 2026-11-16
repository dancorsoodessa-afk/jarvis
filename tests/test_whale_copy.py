from decimal import Decimal

from crypto_analyst.models import Level, MarketTrade, OrderBookSnapshot
from crypto_analyst.whale_copy import WhaleCopyEngine
from crypto_analyst.whale_intel import WhaleTrade


def make_book(now):
    return OrderBookSnapshot(
        symbol="BTC-USDT-SWAP",
        bids=(Level(Decimal("100"), Decimal("500")), Level(Decimal("99.9"), Decimal("10"))),
        asks=(Level(Decimal("100.05"), Decimal("10")), Level(Decimal("100.1"), Decimal("10"))),
        timestamp_ms=now,
        received_at_ms=now,
    )


def make_trades(now):
    return [
        MarketTrade("BTC-USDT-SWAP", "buy", Decimal("100.05"), Decimal("2"), now - 100),
        MarketTrade("BTC-USDT-SWAP", "buy", Decimal("100.05"), Decimal("3"), now - 50),
    ]


def whale(now, raw=None, address="0x" + "a" * 40):
    return WhaleTrade(
        timestamp=str(now - 100),
        address=address,
        coin="BTC",
        side="buy",
        price=Decimal("100"),
        size_usd=Decimal("500000"),
        venue="Nansen",
        raw=raw or {},
    )


def test_whale_copy_requires_ranked_wallet_and_confirming_okx_flow():
    now = 1_700_000_000_000
    engine = WhaleCopyEngine(whitelist={"BTC-USDT-SWAP"})
    signal = engine.evaluate(whale(now), {("0x" + "a" * 40).upper()}, make_book(now), make_trades(now), now)
    assert signal is not None
    assert signal.side == "buy"
    assert "Paper only" in signal.reason


def test_whale_copy_rejects_stale_or_unranked_wallet():
    now = 1_700_000_000_000
    engine = WhaleCopyEngine()
    stale = WhaleTrade(
        timestamp=str(now - 60_000), address="0x" + "a" * 40, coin="BTC",
        side="buy", price=Decimal("100"), size_usd=Decimal("500000"),
        venue="Nansen", raw={},
    )
    assert engine.evaluate(stale, {"0x" + "a" * 40}, make_book(now), make_trades(now), now) is None
    assert engine.evaluate(whale(now), set(), make_book(now), make_trades(now), now) is None


def test_whale_copy_rejects_reductions_and_coinglass_position_alerts():
    now = 1_700_000_000_000
    engine = WhaleCopyEngine()
    wallet = "0x" + "a" * 40
    assert engine.evaluate(
        whale(now, {"action": "Sell - Reduce Long"}), {wallet}, make_book(now), make_trades(now), now
    ) is None
    assert engine.evaluate(
        whale(now, {"position_action": 1}), {wallet}, make_book(now), make_trades(now), now
    ) is None


def test_whale_copy_requires_local_orderflow_to_confirm_direction():
    now = 1_700_000_000_000
    engine = WhaleCopyEngine()
    sells = [
        MarketTrade("BTC-USDT-SWAP", "sell", Decimal("100"), Decimal("5"), now - 100),
        MarketTrade("BTC-USDT-SWAP", "sell", Decimal("100"), Decimal("5"), now - 50),
    ]
    assert engine.evaluate(whale(now), {"0x" + "a" * 40}, make_book(now), sells, now) is None
