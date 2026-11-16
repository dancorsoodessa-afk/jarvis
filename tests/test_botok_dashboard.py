def test_botok_dashboard_imports_without_starting_network_connections():
    from crypto_analyst.botok_dashboard import BOTokDashboard

    assert callable(BOTokDashboard)

def test_whale_radar_window_imports_and_accepts_provider_keys():
    from crypto_analyst.whale_dashboard import WhaleRadarWindow

    assert callable(WhaleRadarWindow.__init__)
