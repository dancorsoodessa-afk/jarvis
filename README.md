# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## Android

The Android client is a standalone Flutter application. It connects directly to an OpenAI-compatible cloud endpoint and does not depend on the Windows process.

Android capabilities:
- text chat with configurable primary and fallback AI endpoints;
- Gemini OpenAI-compatible endpoint configured by default; API key must be supplied by the user;
- editable and persistent endpoint, model and API-key settings;
- Russian speech recognition and Russian text-to-speech;
- microphone listening starts when the user taps the mic button, avoiding native speech-service initialization during app startup;
- animated JARVIS reactor with idle, listening, thinking, speaking, confirmation and error states;
- release APK built by GitHub Actions with APK signature, zip alignment, Internet/microphone permission and SHA-256 checks.

### Configure Android AI

Default endpoint:

`https://generativelanguage.googleapis.com/v1beta/openai/`

Default model configured in the app: `gemini-3.8-flash`. Confirm model availability for your Google account in AI Studio before use.

Create a Gemini API key in Google AI Studio and enter it in JARVIS Settings. The model is accessed through the cloud and is not bundled inside the APK. An optional OpenAI-compatible fallback endpoint can be configured separately. Hugging Face and OpenRouter are not used by the Android configuration.

### Tool modules

- `ui/crypto/` — separate crypto center, OKX public market data, indicators and optional CoinGlass endpoints. See its README for limitations.
- `ui/osint/` — separate OSINT screen and service layer for domain/RDAP/DNS, IP/ASN and URL/HTTP lookups. See its README for limitations.
- `agent/tools/osint.py` — Windows/backend OSINT helpers, including domain, IP, URL, email, username and image metadata lookups.

Crypto and OSINT are separate navigation entries; these modules must not be presented as private exchange trading or as guaranteed security verification.

The Android build is intentionally isolated from the Windows executable build.

## Windows

The Windows agent remains a separate target with its existing local AI, tools, memory, STT/TTS and desktop workflows.

Never put API keys, memory files, reminders, or runtime logs into Git.
