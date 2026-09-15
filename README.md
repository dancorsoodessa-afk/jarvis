# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## Android

The Android client is a standalone Flutter application. It connects directly to an OpenAI-compatible AI endpoint and does not depend on the Windows process or Windows IPC.

Android capabilities:
- text chat;
- direct OpenRouter connection;
- free DeepSeek V4 Flash coding-capable model by default;
- persistent endpoint, model and API-key settings;
- Russian microphone voice input;
- automatic wake phrase `Джарвис` while the app is active;
- Russian text-to-speech responses;
- animated JARVIS reactor with idle, listening, thinking, speaking, confirmation and error states;
- release APK built by GitHub Actions.

### Free DeepSeek model for Android

The Android build uses this OpenRouter model by default:

`deepseek/deepseek-v4-flash:free`

OpenRouter currently lists this model as free and describes it as suitable for coding assistants, chat systems and agent workflows.

Endpoint:

`https://openrouter.ai/api/v1`

In JARVIS Android settings, enter the OpenRouter API key and keep the model set to `deepseek/deepseek-v4-flash:free`. The model is accessed through OpenRouter; it is not bundled inside the APK.

The Android build is intentionally isolated from the Windows executable build.

## Windows

The Windows agent remains a separate target with its existing local AI, tools, memory, STT/TTS and desktop workflows.

Never put API keys, memory files, reminders, or runtime logs into Git.
