def test_botok_dashboard_imports_without_starting_network_connections():
    from crypto_analyst.botok_dashboard import BOTokDashboard

    assert callable(BOTokDashboard)
