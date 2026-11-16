from decimal import Decimal

from crypto_analyst.models import MarketTrade, TradingSignal
from crypto_analyst.paper import PaperBroker


def signal():
    return TradingSignal(
        "BTC-USDT-SWAP", "buy",
        Decimal("100"), Decimal("99"), Decimal("102"),
        Decimal("0.4"), Decimal("10"), Decimal("2"), 10_000, "test"
    )


def test_paper_position_closes_on_stop_loss_and_records_net_pnl():
    broker = PaperBroker(Decimal("1000"), maker_fee_rate=Decimal("0"))
    order = broker.place_limit(signal(), Decimal("2"))
    broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "sell", Decimal("100"), Decimal("2"), 10_001
    ))
    assert order.status == "filled"
    assert broker.open_position_count() == 1

    broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "sell", Decimal("98.5"), Decimal("1"), 10_002
    ))
    position = next(iter(broker.positions.values()))
    assert position.status == "closed"
    assert position.exit_price == Decimal("98.5")
    assert position.realized_pnl == Decimal("-3.0")
    assert broker.open_position_count() == 0


def test_paper_broker_does_not_overfill_orders_with_one_trade_print():
    broker = PaperBroker()
    first = broker.place_limit(signal(), Decimal("4"))
    second = broker.place_limit(signal(), Decimal("4"))
    fills = broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "sell", Decimal("99.9"), Decimal("5"), 10_001
    ))
    assert sum(fill.quantity for fill in fills) == Decimal("5")
    assert first.filled_quantity + second.filled_quantity == Decimal("5")
