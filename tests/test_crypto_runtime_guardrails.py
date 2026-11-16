from decimal import Decimal

from crypto_analyst.models import MarketTrade, TradingSignal
from crypto_analyst.paper import PaperBroker


def test_paper_stop_loss_realizes_gross_loss_and_fees_once():
    broker = PaperBroker(Decimal("1000"), maker_fee_rate=Decimal("0.001"))
    signal = TradingSignal(
        "BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("99"),
        Decimal("102"), Decimal("0.4"), Decimal("5"),
        Decimal("2"), 10_000, "test"
    )
    order = broker.place_limit(signal, Decimal("1"))
    broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "sell", Decimal("100"), Decimal("1"), 10_001
    ))
    assert order.status == "filled"
    broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "sell", Decimal("98"), Decimal("1"), 10_002
    ))
    position = next(iter(broker.positions.values()))
    assert position.status == "closed"
    assert position.realized_pnl == Decimal("-2.198")
    assert broker.realized_pnl == Decimal("-2.198")


def test_one_trade_print_cannot_fill_more_than_its_reported_size():
    broker = PaperBroker()
    signal = TradingSignal(
        "BTC-USDT-SWAP", "buy", Decimal("100"), Decimal("99"),
        Decimal("102"), Decimal("0.4"), Decimal("5"),
        Decimal("2"), 10_000, "test"
    )
    first = broker.place_limit(signal, Decimal("3"))
    second = broker.place_limit(signal, Decimal("3"))
    fills = broker.on_trade(MarketTrade(
        "BTC-USDT-SWAP", "sell", Decimal("99.9"), Decimal("4"), 10_001
    ))
    assert sum(item.quantity for item in fills) == Decimal("4")
    assert first.filled_quantity + second.filled_quantity == Decimal("4")
