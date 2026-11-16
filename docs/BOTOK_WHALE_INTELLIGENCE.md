# BOTok: whale intelligence and agent-tool integration

## Desktop workspace

The Crypto Analyst workspace now includes:
- a live OKX price line chart fed by the existing public ticker WebSocket;
- a Whale Radar window with a top-200 Hyperliquid leaderboard and wallet-attributed whale-fill table;
- Start / Stop controls for OKX scanning and Refresh / Pause / Resume controls for the whale feed;
- no authenticated exchange client and no live order placement.

## Whale data sources

### Public / no key
1. Hyperliquid public leaderboard:
   - URL: https://stats-data.hyperliquid.xyz/Mainnet/leaderboard
   - Public opt-in accounts with 24h, 7d, 30d and all-time PnL, ROI, volume and account value.
   - The source is a large static JSON file. BOTok caches it for 15 minutes; do not poll it every few seconds.
   - The current implementation ranks the top 200 by 30-day PnL.
2. CoinLobster public API:
   - https://coinlobster.com/api/public/hyperliquid/whales
   - https://coinlobster.com/api/public/crypto-whales
   - https://coinlobster.com/api/public/whale-radar
   - Public endpoints are rate-limited. The provider controls update cadence and field availability. Exchange trades are often anonymous; wallet identity is available for Hyperliquid/on-chain fills where supplied by the provider.

### Optional paid API: CoinGlass

Set COINGLASS_API_KEY in the Whale Radar key field to enable:
- GET /api/hyperliquid/whale-position: current Hyperliquid positions larger than USD 1 million, including wallet, symbol, signed position size, entry/mark/liquidation prices, leverage, unrealized PnL and funding fee.
- GET /api/hyperliquid/whale-alert: recent position-open/close tracking alerts above USD 1 million. These are position tracking events, not individual buy/sell fills; create_time is not guaranteed to be the actual exchange open/close time.
- CoinGlass documents these Hyperliquid whale endpoints as real-time and requires Startup or higher API plan. The API key is sent in the CG-API-KEY header. The Whale Radar displays the top 200 largest current positions and recent alerts in separate tabs.
- Keys entered in the Windows BOTok panel are encrypted with the existing Windows DPAPI helper and saved in the user's JARVIS settings file. They are not committed to Git.

CoinGlass is the strongest complementary source for large Hyperliquid positions and liquidation context. It does not by itself rank the 200 most profitable traders; use Nansen or the Hyperliquid leaderboard for performance ranking.

### Optional paid API: Nansen
Set NANSEN_API_KEY in the process environment to enable:
- POST https://api.nansen.ai/api/v1/perp-leaderboard: top 200 Hyperliquid perp traders by total PnL for a rolling 30-day window.
- POST https://api.nansen.ai/api/v1/smart-money/perp-trades: recent Smart HL Perps Trader fills (24-hour lookback; endpoint supports up to seven days).
- Nansen uses API credits and subscription tiers. Premium Smart Money/Fund labels cost more and are not requested by the default implementation. The dashboard increases its polling interval to five minutes when this key is configured to avoid unnecessary credit consumption.
- Do not commit the key to Git. Use a local environment variable or a secret manager.

Nansen is the better option for ranked Hyperliquid perp traders plus labeled smart-money fills. CoinLobster is the lower-friction option for multi-exchange whale trades. Neither provides a universal, complete identity map of the top 200 traders across every centralized exchange.

## What “top 200 whales” actually means

BOTok's public fallback is top 200 opted-in Hyperliquid leaderboard accounts by 30-day PnL, not the 200 richest crypto wallets worldwide. A leaderboard rank is not proof of skill: account aliases can be absent, one operator can control multiple wallets, and a high-volume market maker can be profitable without providing a useful directional signal.

Centralized exchange order books and public Time & Sales generally do not reveal the identity of the account behind every order. Wallet attribution is available only where a chain or provider exposes it. Transfers are not trades; a large transfer can be an exchange deposit, custody movement or internal wallet shuffle.

## Agent frameworks evaluated

- TauricResearch/TradingAgents (Apache-2.0): multi-agent research/debate pattern. Use as a strategic analysis design reference for bull/bear, technical, sentiment, trader and risk roles. It is not wired into the low-latency execution loop.
- virattt/ai-hedge-fund (MIT): investor-agent and paper-fund workflow reference. Its README explicitly says it is educational and does not execute actual trades. Its current data assumptions are not a direct drop-in for OKX scalping.
- tradermonty/claude-trading-skills (MIT): risk, journaling, pre-trade discipline and review workflows. Its README explicitly says it is not designed for fully automated trading or short-term scalping. Use only the reusable checklists and review patterns, not its swing-trading strategy as a scalping signal.

No external repository is blindly vendored into BOTok. These are separate upstream projects with their own dependencies, providers, data models and licenses. BOTok keeps its existing deterministic Python risk gate and OKX Paper Broker as the execution authority.

## Copy-trading safety pipeline (next stage)

A whale fill must never directly create an order. The intended pipeline is:

1. Identify the wallet and verify it is in the current 200-account cohort.
2. Validate timestamp, token, direction, notional and source freshness.
3. Detect whether the fill opens, adds, reduces or closes exposure; do not mistake a reduction for a new entry.
4. Compare the wallet action with current OKX book imbalance, trade delta/CVD, spread, depth, funding, open interest and liquidation context.
5. Reject stale, conflicting, illiquid or overextended conditions.
6. Run independent position sizing, max exposure, daily loss, slippage and liquidation-distance checks.
7. Create a Paper Broker order only. Record the source wallet, source fill, decision evidence and simulated outcome.
8. Promote a strategy only after out-of-sample / walk-forward validation and a stable paper record.

Current boundary: the Whale Radar is a read-only monitoring panel. Its fills are not yet routed into Paper Broker copy orders. The existing OKX scalping engine remains separate. No live exchange order execution is present or permitted.

## External MCP tool

CoinLobster documents a hosted MCP endpoint at https://coinlobster.com/mcp. It is not listed as an installable ChatGPT plugin in the current plugin search. BOTok currently uses the documented public REST endpoints; no claim is made that the MCP server has been connected to ChatGPT or installed in Jarvis.
