# BOTok: smart-money, agent research and whale tracking

## Branch

The working branch is BOTok. The branch currently points at the paper-only OKX Crypto Analyst baseline. It is not yet the repository default branch; GitHub repository administration is required to change the default branch from foundation to BOTok.

## Research components evaluated

### TradingAgents
Repository: https://github.com/TauricResearch/TradingAgents

Use as an architectural reference for multi-agent debate and role separation (research, analyst, risk, portfolio). Its core project is a general financial-market research framework, not a drop-in OKX crypto execution engine. BOTok should adapt the agent separation, not copy its stock-specific data assumptions or grant LLMs order authority.

### TapeSkills trader-skills
Repository: https://github.com/Tapeskills/trader-skills

The Backtest Sanity Checker skill is relevant to BOTok. Use its checklist for look-ahead bias, unrealistic fills, fees, slippage, sample size and overfitting. The SEC Filing Finder is equity-specific and is not part of the crypto runtime. Skills are review procedures, not live market-data feeds.

### AI Hedge Fund
Repository: https://github.com/virattt/ai-hedge-fund

This is explicitly an educational proof of concept and its README states that it does not actually place trades. Treat it as a reference for specialist investor-agent roles and human-readable reasoning only; do not import its execution assumptions or present it as a production crypto bot.

## Whale-data sources

### Primary candidate: Nansen MCP
Official MCP endpoint: https://mcp.nansen.ai/ra/mcp/
Required secret: NANSEN_API_KEY (obtain from https://app.nansen.ai/api).

Nansen documents Smart Money labels, wallet profiling, token analytics, Smart Money DEX trades and flow endpoints. BOTok includes an optional Streamable-HTTP MCP client that discovers the live server tool schema. It does not hard-code unverified tool names. The UI must show the provider as disconnected until the key is configured and a live handshake succeeds.

### CoinGlass: live large Hyperliquid positions
API endpoint: https://open-api-v4.coinglass.com/api/hyperliquid/whale-position
Required secret: COINGLASS_API_KEY (header CG-API-KEY).

The documented endpoint returns current Hyperliquid positions larger than USD 1 million, including wallet, symbol, signed position size, entry/mark/liquidation prices, leverage, margin, unrealized PnL and update time. The adapter groups multiple positions by wallet and displays the 200 largest gross-position accounts. This is a snapshot endpoint, not a guaranteed sub-second push feed; the UI refreshes it on demand and then every 60 seconds while results are available. CoinGlass plan permissions and rate limits apply.

### Bitquery: strongest candidate for best-trader ranking and trade stream
Official Top Traders API: https://www.bitquery.io/products/trade-api
Bitquery describes wallet leaderboards ranked by realized PnL, volume, trade count and win-rate, plus WebSocket/gRPC streaming of DEX trades. This is the better source for ranking consistently profitable traders and observing their actual DEX swaps, rather than using open-position size as a proxy for skill. A Bitquery API token and plan with streaming permissions are required. The Bitquery connector is not yet enabled in the BOTok runtime.

### Secondary sources to evaluate
- Arkham Intelligence: entity attribution and investigation; useful for checking whether an address is an exchange, fund, market maker or other known entity.
- Bitquery: programmable multi-chain transfer/DEX-trade data and streaming; useful for building a custom watchlist and event pipeline.
- Whale Alert: large-transfer alerts; treat transfers as leads, not proof of a buy or sell.
- CoinGlass: exchange derivatives context such as open interest, funding, liquidations and its whale/large-position dashboards.
- Hyperliquid public endpoints: wallet positions and trade activity for the Hyperliquid ecosystem.

## Definition of the top 200

Do not claim there is a universal public list of the world's 200 richest or best traders. BOTok should maintain a configurable, rolling top-200 cohort per supported chain/venue, ranked by a transparent composite of:
1. realized PnL over a defined window;
2. win rate and trade count, with a minimum sample threshold;
3. net flows and consistency;
4. wallet/entity attribution confidence;
5. recency of activity.

Exclude exchange hot wallets, bridges, routers, custodians and obvious infrastructure addresses where labels permit. Keep source, observation time, chain, transaction hash and freshness for every event. Large balance alone is not a skill score.

## Signal-to-paper workflow

1. Ingest a wallet event or a public trade/position update.
2. Resolve labels and counterparties; reject unclassified transfers as low-confidence.
3. Determine whether it is an actual swap/trade, a deposit/withdrawal, a bridge, collateral movement or liquidation.
4. Deduplicate transaction hashes and wallet-event IDs.
5. Score the wallet cohort and event quality.
6. Correlate with OKX order book, trades, funding, open interest, liquidations and technical context.
7. Run the deterministic BOTok risk gate and spread/slippage checks.
8. Create a Paper Trading order only. No real exchange order path is permitted.

Wallet activity is an independent confirmation input, not a standalone entry trigger. Copying a whale after its transaction becomes public can be late and suffer adverse selection.

## Current integration status

- The BOTok branch has an optional Nansen MCP client that discovers the live tool schema and requires NANSEN_API_KEY.
- The BOTok branch has a CoinGlass Hyperliquid whale-position client and aggregates the top 200 largest open-position wallets; it requires COINGLASS_API_KEY.
- Windows UI key fields save Nansen and CoinGlass keys encrypted with the existing Windows DPAPI helper in the user's JARVIS settings file.
- No API keys are stored in GitHub or committed to source.
- Bitquery Top Traders is documented as the preferred realized-PnL/win-rate and DEX trade stream source, but its runtime adapter is not yet implemented.
- No Arkham or Whale Alert credentials are configured.
- The current OKX market feed remains public and read-only.
- The trading engine remains Paper Trading only; there is no live exchange order placement.
- The top-200 ranking helper ranks only rows actually returned by a configured provider. It does not fabricate wallet identities or events.
