# JARVIS CRYPTO

All crypto-specific code is grouped in this package:

- `market.py` — public market-data connectors for Binance Spot, Bybit Spot and OKX Spot.
- `analysis.py` — EMA 9/21/50, RSI 14, ATR 14, local support/resistance and transparent LONG/SHORT/HOLD classification.
- `risk.py` — conservative Spot position sizing, stop-loss and take-profit calculations.
- `window.py` — button-first Tkinter dashboard, exchange comparison, optional 20-second refresh and local trade-plan journal.

## Safety and data rules

- Uses public market endpoints; API keys are not required.
- Does not submit, amend or cancel orders.
- Does not access balances or withdraw funds.
- Displays the exchanges that actually returned data.
- If all public sources fail, the dashboard displays NO DATA and suppresses the signal.
- Risk per plan is limited to 2% of the entered capital; leverage is disabled in this first iteration.
- Saved plans are written to `%APPDATA%\JARVIS\crypto\trade_plans.json` (or the user's home directory on non-Windows systems).

This is an initial working foundation, not a profitability guarantee. It does not yet implement futures funding/open-interest/liquidation feeds, news scoring, portfolio sync, or live order execution.
