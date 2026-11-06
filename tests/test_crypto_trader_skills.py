import json
import pytest
from agent.crypto import trader_skills as crypto

def test_budget_reserves_cash_and_caps_position():
    result=crypto.trader_budget(1000,10,20)
    assert (result["cash_reserve"],result["investable"],result["max_position"])==(100,900,200)

def test_risk_calculates_position_size():
    result=crypto.trader_risk(1000,100,95,1)
    assert result["risk_cash"]==10 and result["quantity"]==2 and result["leverage"]==1

def test_broker_creates_paper_ticket_only(tmp_path):
    ticket=crypto.trader_broker("BTCUSDT","buy",.01,50000,str(tmp_path))
    saved=json.loads((tmp_path/"paper_orders.json").read_text())
    assert ticket["status"]=="PAPER_PENDING" and len(saved)==1 and saved[0]["side"]=="BUY"

def test_broker_rejects_invalid_side(tmp_path):
    with pytest.raises(ValueError): crypto.trader_broker("BTC-USDT","SHORT",1,100,str(tmp_path))

def test_fifo_tax_calculates_realized_profit():
    result=crypto.trader_tax('[{"quantity":2,"buy_price":10},{"quantity":2,"buy_price":20}]',3,25)
    assert result["cost_basis"]==40 and result["proceeds"]==75 and result["realized_pnl"]==35
    assert result["remaining_lots"][1]["quantity"]==1

def test_fifo_rejects_oversell():
    with pytest.raises(ValueError): crypto.trader_tax('[{"quantity":1,"buy_price":10}]',2,20)

def test_alerts_only_triggered_thresholds():
    assert crypto.trader_alerts("BTC",105,above=100,below=90)[0]["condition"]=="ABOVE"
    assert crypto.trader_alerts("BTC",95,above=100,below=90)==[]

def test_rebalance_calculates_buy_and_sell_deltas():
    rows=crypto.trader_rebalance('[{"asset":"BTC","target_pct":60,"current_value":40},{"asset":"ETH","target_pct":40,"current_value":60}]',100)
    assert [x["action"] for x in rows]==["BUY","SELL"] and [x["delta"] for x in rows]==[20,-20]

def test_rebalance_requires_100_percent_targets():
    with pytest.raises(ValueError): crypto.trader_rebalance('[{"asset":"BTC","target_pct":80}]',100)

def test_symbol_normalization():
    assert crypto._symbol(" btc/usdt ")=="BTC-USDT"
