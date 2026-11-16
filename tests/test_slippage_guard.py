from decimal import Decimal

from crypto_analyst.models import Level, OrderBookSnapshot
from crypto_analyst.slippage_guard import estimate_book_slippage_bps


def sample_book():
    return OrderBookSnapshot(
        "BTC-USDT",
        (Level(Decimal("100"), Decimal("2")), Level(Decimal("99"), Decimal("5"))),
        (Level(Decimal("101"), Decimal("2")), Level(Decimal("102"), Decimal("5"))),
        10_000, 10_000,
    )


def test_slippage_guard_calculates_depth_vwap():
    assert estimate_book_slippage_bps(sample_book(), "buy", Decimal("2")) == 0
    assert estimate_book_slippage_bps(sample_book(), "buy", Decimal("3")) > 0
    assert estimate_book_slippage_bps(sample_book(), "sell", Decimal("3")) > 0


def test_slippage_guard_rejects_quantity_beyond_visible_depth():
    assert estimate_book_slippage_bps(sample_book(), "buy", Decimal("10")) is None
