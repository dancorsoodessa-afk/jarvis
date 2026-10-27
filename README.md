# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## Android

The Android client is a standalone Flutter application. It connects directly to an OpenAI-compatible cloud endpoint and does not depend on the Windows process.

Android capabilities:
- text chat with configurable primary and fallback AI endpoints;
- Groq as the default provider, using the `openai/gpt-oss-20b` model;
- editable and persistent endpoint, model and API-key settings;
- Russian speech recognition and Russian text-to-speech;
- microphone listening starts when the user taps the mic button, avoiding native speech-service initialization during app startup;
- animated JARVIS reactor with idle, listening, thinking, speaking, confirmation and error states;
- release APK built by GitHub Actions with APK signature, zip alignment, Internet/microphone permission and SHA-256 checks.

### Configure Android AI

Default endpoint:

`https://api.groq.com/openai/v1`

Default model:

`openai/gpt-oss-20b`

Create a Groq API key and enter it in JARVIS Settings. The model is accessed through the cloud and is not bundled inside the APK. An optional OpenAI-compatible fallback endpoint can be configured separately. Hugging Face and OpenRouter are not used by the Android configuration.

The Android build is intentionally isolated from the Windows executable build.

## Windows

The Windows agent remains a separate target with its existing local AI, tools, memory, STT/TTS and desktop workflows.

Never put API keys, memory files, reminders, or runtime logs into Git.
