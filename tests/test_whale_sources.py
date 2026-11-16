from crypto_analyst.whale_sources import NansenMCPClient, rank_whale_wallets


def test_rank_whales_uses_performance_and_returns_top_200():
    rows = [
        {"wallet": f"0x{i:040x}", "realized_pnl_usd": i * 1000, "win_rate": 0.7,
         "net_flow_usd": i * 100, "trade_count": 50}
        for i in range(250)
    ]
    ranked = rank_whale_wallets(rows)
    assert len(ranked) == 200
    assert ranked[0].realized_pnl_usd > ranked[-1].realized_pnl_usd


def test_rank_whales_skips_rows_without_wallet_address():
    assert rank_whale_wallets([{"realized_pnl_usd": 1000}]) == []


def test_nansen_client_requires_api_key_before_network_access():
    client = NansenMCPClient(api_key="")
    assert not client.configured
    try:
        client.initialize()
    except RuntimeError as exc:
        assert "NANSEN_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing API key to fail closed")


def test_nansen_tool_name_must_be_nonempty():
    client = NansenMCPClient(api_key="test-key")
    try:
        client.call_tool(" ", {})
    except ValueError as exc:
        assert "Tool name" in str(exc)
    else:
        raise AssertionError("Expected empty tool name to fail")
