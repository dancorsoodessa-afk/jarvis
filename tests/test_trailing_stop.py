from decimal import Decimal
from types import SimpleNamespace

from crypto_analyst.trailing_stop import TrailingStopManager


def test_long_trailing_stop_only_moves_up():
    position = SimpleNamespace(
        status="open", side="buy", entry_price=Decimal("100"),
        favorable_price=Decimal("100"), stop_loss=Decimal("99")
    )
    manager = TrailingStopManager(Decimal("30"))
    assert manager.update(position, Decimal("101")) == Decimal("100.697")
    assert manager.update(position, Decimal("100")) == Decimal("100.697")


def test_short_trailing_stop_only_moves_down():
    position = SimpleNamespace(
        status="open", side="sell", entry_price=Decimal("100"),
        favorable_price=Decimal("100"), stop_loss=Decimal("101")
    )
    manager = TrailingStopManager(Decimal("30"))
    assert manager.update(position, Decimal("99")) == Decimal("99.297")
    assert manager.update(position, Decimal("100")) == Decimal("99.297")
