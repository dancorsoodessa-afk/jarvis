# JARVIS Crypto module

This module is designed to be isolated from voice and operating-system tools.

## Included in the Android client
- Public OKX spot tickers for BTC, ETH, SOL and XRP
- OHLCV candles for configurable instrument/timeframe
- Basic SMA20/SMA50, RSI14 and observed-period price change
- Public perpetual swap funding rate and open interest
- Visible errors and refresh action; no API key required for public endpoints

## Not implemented by this public-data screen
- CoinGlass liquidation/CVD/long-short endpoints (requires provider-specific API access)
- Private balances, positions, portfolio history or exchange order placement
- Trading signals validated by backtests

Never put withdrawal permission on exchange API keys. Real order execution must be a separate, explicit-confirmation feature.
