# BOTok — Whale Intelligence and AI Trading Architecture

## Branch and safety

Development branch: BOTok.

The current exchange engine remains OKX public market data + deterministic Paper Trading. No authenticated exchange client, no live order-placement method, and no real exchange API keys are added. Whale events may create a candidate paper signal only after the existing risk manager approves it. No blind copy trading.

## External research projects

- TauricResearch/TradingAgents (Apache-2.0): use its analyst/debate/manager separation as an architectural reference for strategic research. Do not copy its equity-market data assumptions into the crypto execution loop.
- virattt/ai-hedge-fund (MIT): use the investor-agent decomposition, fund mandate and ledger concepts as research references. Its README explicitly says it is educational and does not actually place trades; it is not an exchange execution engine.
- CoinLobster/agent-skills (MIT): use the read-only whale-flow, whale-radar, market-snapshot and liquidation-analysis workflows. Attribution is retained; the integration uses documented public GET endpoints and does not copy opaque binaries.

## Whale data adapter

crypto_analyst/whale_intel.py connects to the documented keyless CoinLobster public endpoints:
- /api/public/crypto-whales — large executed CEX trades
- /api/public/hyperliquid/whales — Hyperliquid fills with wallet addresses
- /api/public/onchain-whales — DEX swaps on Ethereum in the free public view
- /api/public/hyperliquid/board — provider-tracked Hyperliquid accounts
- /api/public/whale-radar — unusual whale-flow coins

The public API is rate-limited (60 requests/minute per IP). The desktop refresh cadence is deliberately slow and should honor Retry-After. The public feed is not uniformly real-time: CoinLobster documents BTC/USD and $1M+ trades as live, with most other free-tier pairs delayed by 15 minutes. The free DEX endpoint is a limited teaser feed. Full pair coverage/depth requires the provider's paid developer plan; a CoinLobster website subscription is not equivalent to API access.

## Important identity and ranking limits

- CEX trade prints show venue/side/price/size, not the identity of the trader. A $5M trade cannot be assigned to a specific whale without a separately verified identity source.
- Hyperliquid public fills can include wallet addresses; the public board is a provider-tracked set, not a guaranteed ranked list of the 200 most profitable traders.
- BOTok displays up to 200 rows returned by the provider, never fabricates missing wallets, rankings, PnL or trade history.
- For a true top-200-by-performance universe, add a licensed source that supplies realized PnL, closed-trade history and wallet labels (e.g. Bitquery custom streams or Nansen Smart Money/API). A wallet balance or equity is not a profitability score.

## Decision pipeline

1. Ingest OKX market streams and CoinLobster whale events independently.
2. Normalize event source, asset, side, USD notional, venue, wallet, timestamp and transaction/trade ID.
3. Deduplicate and check timestamp freshness; label delayed, stale and unavailable feeds explicitly.
4. Resolve wallet attribution only from source-provided labels/addresses.
5. Score trader history only when realized PnL, closed trades, sample size and observation window are present.
6. Compare whale direction with OKX order-book imbalance, CVD, funding, open interest, liquidation pressure and price structure.
7. Create a candidate LONG/SHORT paper signal; deterministic risk checks remain mandatory.
8. Simulate paper limit fills, fees, partial fills, SL/TP and trailing stops. Record the source whale event and the resulting paper outcome.

## Desktop controls

The BOTok workspace is designed around a live price chart, whale tape, provider-tracked Hyperliquid accounts, signal log, virtual balance, and Start / Stop / Emergency Stop controls. Emergency Stop stops all data workers and prevents new paper orders; it does not cancel or send anything to an exchange.

## Planned / not yet verified

- Live API response shape and latency must be checked against a real network session.
- The 200-account provider board count and ranking methodology must be confirmed from actual returned payloads.
- Paid Bitquery/Nansen access and credentials are not provisioned.
- Full 200-wallet performance scoring and copy-paper strategy are not implemented until verified realized-PnL history is available.
- No live execution or VPS provisioning is enabled.
