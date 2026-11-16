# Crypto Analyst implementation status

## Implemented in the feature branch

- OKX public WebSocket client with reconnect/backoff for books5, trades, and tickers.
- Public instrument discovery for live USDT spot and USDT-settled swap instruments.
- In-memory normalized order books, tickers, and bounded trade history.
- Weighted depth imbalance, visible liquidity-wall heuristic, trade delta, and repeated-price volume heuristic.
- Deterministic signal generation with whitelist, spread, freshness, and trade-flow filters.
- Risk checks for position size, daily loss, max exposure, spread, data age, and reward/risk.
- Paper-only order and position simulation with partial fills, maker fee estimate, and virtual stop/target exits.
- YouTube channel RSS monitoring, optional transcript retrieval, and schema-validated LLM hypothesis extraction.
- Unit tests for the above modules.

## Explicitly not complete yet

- Desktop Crypto Analyst screen and navigation wiring.
- Full-market scanning policy, subscription batching, liquidity ranking, and instrument refresh scheduler.
- Redis cache/stream and PostgreSQL persistence.
- Historical market replay, realistic queue-position simulation, and walk-forward backtesting.
- Production monitoring, latency SLOs, and VPS deployment automation.
- Final Windows EXE build and runtime smoke test.

## Safety

The implementation has no authenticated OKX account connection and no live order placement method. The trading module is paper-only. YouTube hypotheses are research inputs, not trade instructions; the deterministic risk gate remains mandatory.
