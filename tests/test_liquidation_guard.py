from decimal import Decimal

from crypto_analyst.liquidation_guard import estimate_linear_liquidation_price, stop_is_clear_of_liquidation


def test_linear_liquidation_estimate_for_long_and_short():
    assert estimate_linear_liquidation_price(Decimal("100"), "buy", Decimal("2")) == Decimal("50.500")
    assert estimate_linear_liquidation_price(Decimal("100"), "sell", Decimal("2")) == Decimal("149.500")


def test_stop_must_remain_clear_of_estimated_liquidation():
    assert stop_is_clear_of_liquidation(Decimal("100"), Decimal("99"), "buy", Decimal("2"))
    assert not stop_is_clear_of_liquidation(Decimal("100"), Decimal("50.2"), "buy", Decimal("2"))
    assert not stop_is_clear_of_liquidation(Decimal("100"), Decimal("149.8"), "sell", Decimal("2"))
