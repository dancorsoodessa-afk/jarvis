# JARVIS — Windows desktop assistant

JARVIS is a Windows desktop assistant with a graphical interface, OS tools, voice services, and a cloud AI backend.

## Crypto Analyst

The Windows desktop sidebar opens a separate **CRYPTO ANALYST / PAPER** workspace. The headless Linux worker can run independently on a VPS or in Docker.

### Market data

- OKX public WebSocket only; no exchange account key is required.
- Live USDT spot and USDT-settled swap instrument discovery.
- Liquidity ranking with a configurable minimum 24-hour quote turnover and a 500-instrument scan cap.
- Sharded WebSocket subscriptions for books5, trades, tickers, open-interest, funding-rate, and public liquidation-orders.
- Automatic reconnect, backoff, text heartbeat, and in-memory state.
- The order-book feed currently uses OKX books5 snapshots. It does not reconstruct the full 400-level incremental books channel.

### Analysis and decisions

- Weighted Bid/Ask imbalance, visible liquidity walls, trade delta/CVD primitives, and repeated-price execution heuristics.
- EMA, RSI, MACD, VWAP, Bollinger Bands, and ATR calculation primitives.
- Fair Value Gap, Break of Structure, and Change of Character detection primitives.
- Deterministic LONG/SHORT signal generation from order-book imbalance and trade-flow confirmation.
- Contract-aware position sizing using OKX ctVal and ctMult.
- Risk limits for per-trade loss, daily drawdown, exposure count, spread, visible-depth slippage, and estimated liquidation distance.
- Virtual Maker-first limit orders, partial fills, fees, position tracking, stop-loss, take-profit, and trailing stops.

### Strategic YouTube layer

- Polls channel RSS feeds for new videos.
- Retrieves available captions with youtube-transcript-api.
- Uses the Gemini provider to extract structured hypotheses, assets, zones, invalidation levels, targets, timeframe, confidence, and source metadata.
- Channel IDs are supplied through JARVIS_YOUTUBE_CHANNEL_IDS.
- Transcript availability depends on the video's caption access. Extracted hypotheses are research inputs, not automatic trade commands.

### Storage, replay, and deployment

- Redis caches recent order books and stores raw market events in a bounded stream.
- PostgreSQL journals signals, orders, fills, closed positions, and YouTube hypotheses.
- Chronological event replay and initial performance metrics are available; realistic queue-position modelling and walk-forward validation remain future work.
- Dockerfile.crypto and docker-compose.crypto.yml provide a headless worker stack with Redis and PostgreSQL.

**Safety boundary:** Crypto Analyst is paper-only. There is no authenticated OKX trading client, no API-key storage for the exchange, and no live order-placement method. Binance is not integrated. The paper fill model is simplified and is not exchange-grade queue simulation. The estimated liquidation formula is a conservative approximation, not the exchange's exact liquidation engine. Python/asyncio is suitable for millisecond-level event processing, not guaranteed microsecond HFT.

The OKX public feed uses the lightweight websockets client directly. CCXT Pro is not required for the OKX-only implementation.

## Windows installation and build

The current repository targets Python >=3.10,<3.13; the GitHub Windows workflow uses Python 3.12.

```powershell
python -m pip install --upgrade pip
python -m pip install poetry
python -m pip install -e ".[all]"
python -m pip install "pyinstaller>=6.22,<7" pytest
powershell -ExecutionPolicy Bypass -File scripts\\build_exe.ps1
```

The build script runs tests before packaging. The executable is written to release\\JARVIS.exe. A successful GitHub test run does not by itself prove the packaged EXE launches correctly on the user's PC.

## Headless Crypto Worker (VPS / Docker)

1. Copy .env.crypto.example to .env.
2. Set a strong alphanumeric POSTGRES_PASSWORD.
3. Optionally set GEMINI_API_KEY, JARVIS_YOUTUBE_CHANNEL_IDS, and JARVIS_STRATEGIC_MODEL.
4. Start the stack:

```bash
docker compose --env-file .env -f docker-compose.crypto.yml up --build -d
```

5. Inspect logs:

```bash
docker compose --env-file .env -f docker-compose.crypto.yml logs -f crypto-worker
```

Redis and PostgreSQL are internal to the Compose network; do not expose their ports publicly. The Compose stack prepares the worker but does not provision or pay for a VPS. Actual VPS deployment requires a host and credentials.

## Existing JARVIS features

- Primary AI: Google Gemini.
- Optional chat fallback: Groq.
- Voice recognition and speech output: see the current voice settings in the desktop control center.
- 3D interface: local Three.js/WebGL scene.

Do not commit API keys to Git or paste them into source files. Android source remains separate from the Windows desktop application.
