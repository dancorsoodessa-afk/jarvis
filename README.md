# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## Android

The Android client is a standalone Flutter application. It connects directly to an OpenAI-compatible AI endpoint and does not depend on the Windows process or Windows IPC.

Android capabilities:
- text chat;
- automatic model discovery through `/models` when no model is specified;
- local conversation history in the running app;
- microphone voice input with Russian speech recognition;
- automatic wake phrase `Джарвис` while the app is active;
- Russian text-to-speech responses;
- animated JARVIS reactor with idle, listening, thinking, speaking, confirmation and error states;
- release APK built by GitHub Actions.

### Free DeepSeek Coder

For a completely free local coding model, use Ollama with DeepSeek Coder 6.7B Instruct:

```powershell
ollama pull deepseek-coder:6.7b-instruct
```

Then run it with:

```powershell
ollama run deepseek-coder:6.7b-instruct
```

Ollama exposes the local API on port `11434`. The Android JARVIS client can use an OpenAI-compatible Ollama endpoint when the PC is reachable from the phone over the local network. The model itself is not bundled into the APK because the 6.7B model is several gigabytes; it remains installed locally on the PC.

For free cloud coding through OpenRouter, the current free DeepSeek coding-capable model is `deepseek/deepseek-v4-flash:free`. The OpenRouter endpoint remains:

`https://openrouter.ai/api/v1`

The Android client should use the OpenRouter API key only for OpenRouter models; the local Ollama connection does not require an OpenRouter key.

The Android build is intentionally isolated from the Windows executable build.

## Windows

The Windows agent remains a separate target with its existing local AI, tools, memory, STT/TTS and desktop workflows.

Never put API keys, memory files, reminders, or runtime logs into Git.
