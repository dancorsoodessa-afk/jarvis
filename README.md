# JARVIS — Windows desktop assistant

JARVIS is a Windows desktop assistant with a graphical interface, memory, OS tools, and a cloud AI backend.

## Architecture

- **Primary cloud AI:** Google Gemini API using the official OpenAI-compatible endpoint.
- **Independent chat fallback:** Groq Cloud, configured with its own optional API key, model, timeout, and live endpoint check. If Groq is not configured, it is explicitly reported as unavailable.
- **Voice recognition:** microphone capture on the PC plus cloud Gemini transcription; requires internet and the Gemini API key.
- **Voice output:** cloud Gemini TTS with a configurable voice, model, and timeout.
- **3D interface:** real Three.js/WebGL neural reactor served locally and opened in the browser. The scene reacts to live microphone level and the assistant's listening, thinking, speaking, and error states.
- **Camera:** not implemented; JARVIS does not request camera access.

## Crypto Analyst — paper-only development module

The `crypto_analyst/` package contains the first backend layer for an OKX-only market-data and paper-scalping workflow:

- Public OKX WebSocket subscriptions for `books5`, `trades`, and `tickers`.
- In-memory normalized order-book, trade, and ticker state.
- Weighted Bid/Ask imbalance, visible liquidity-wall heuristics, and aggressor trade delta.
- Deterministic signal generation with whitelist, freshness, and spread filters.
- A separate risk gate for position sizing, daily loss, leverage, and reward/risk checks.
- A paper broker driven by public trade prints.

**Safety boundary:** the module is paper-only. It has no authenticated OKX account connection, API-key handling, or live order-placement method. Public order-book walls and repeated executions are heuristics, not proof of hidden liquidity or iceberg orders. The initial paper fill model is a simplified simulation and must not be treated as exchange-grade queue simulation.

The public feed uses the lightweight `websockets` client directly against OKX because this repository targets OKX only. CCXT Pro can be added as an optional adapter if a licensed CCXT Pro deployment is selected; it is not required for the current OKX-only feed.

The `strategic/` package adds channel RSS monitoring, optional transcript retrieval through `youtube-transcript-api`, and an injected-LLM extractor that validates hypotheses and preserves source video metadata. Transcript availability depends on YouTube caption access. The extractor treats transcript text as untrusted input and is deliberately separate from the scalping loop.

The package is a backend foundation and is not yet represented as a completed desktop trading screen. UI wiring, persistent storage, replay/backtesting, and end-to-end Windows release verification remain subsequent implementation work.

## Get the free Gemini API key

1. Open [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create an API key for a project with Gemini API free-tier access.
3. Open JARVIS → **Центр управления** and paste the key into **GEMINI API KEY**.
4. Save and restart the core.

Alternatively, for the current PowerShell session:

```powershell
$env:GEMINI_API_KEY = "your_gemini_api_key"
```

Default model: `gemini-3.8-flash`. The free tier has model-specific rate limits and may change. Do not enable billing if you require strictly free usage. Free-tier requests may be subject to Google's data-use terms; review the current policy before sending sensitive data.

## Build on Windows

```powershell
python -m pip install --upgrade pip
python -m pip install poetry
python -m pip install -e ".[all]"
python -m pip install "pyinstaller>=6.22,<7" pytest
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script runs tests before packaging. The executable is written to `release\JARVIS.exe`.

## Voice

- Input: microphone audio is recorded locally and sent to Gemini for Russian transcription.
- Output: Gemini cloud TTS generates a WAV voice response using the same Gemini API key.
- Internet access is required for both cloud recognition and speech generation. If a service is unavailable, JARVIS reports the error rather than silently switching to a different voice engine.
- Configure the TTS model, voice, and request timeout in the control center.
- Check Windows microphone permissions and the selected input device if recording fails.

## Run from source

Prepare the pinned local Three.js engine once, then launch the app:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_3d_assets.ps1
python -m agent
python jarvis_desktop.py
```

Do not commit API keys to Git or paste them into source files. Android source is preserved for later work.
