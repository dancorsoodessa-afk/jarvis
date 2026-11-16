from decimal import Decimal

import pytest

from crypto_analyst.backtesting import performance_report


def test_performance_report_calculates_key_metrics():
    report = performance_report(
        [Decimal("100"), Decimal("-50"), Decimal("25"), Decimal("-25")],
        starting_equity=Decimal("1000"),
    )
    assert report.trade_count == 4
    assert report.wins == 2 and report.losses == 2
    assert report.win_rate == 0.5
    assert report.net_profit == Decimal("50")
    assert report.profit_factor == pytest.approx(125 / 75)
    assert float(report.max_drawdown) == pytest.approx(50 / 1100)


def test_performance_report_rejects_non_finite_pnl():
    with pytest.raises(ValueError, match="finite"):
        performance_report([Decimal("NaN")])
