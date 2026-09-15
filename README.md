# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## Android

The Android client is a standalone Flutter application. It connects directly to an OpenAI-compatible AI endpoint and does not depend on the Windows process or Windows IPC.

Android capabilities:
- text chat;
- automatic model discovery through `/models` when no model is specified;
- local conversation history in the running app;
- microphone voice input with Russian speech recognition;
- animated JARVIS reactor with idle, listening, thinking, speaking, confirmation and error states;
- release APK built by GitHub Actions.

The Android build is intentionally isolated from the Windows executable build.

## Windows

The Windows agent remains a separate target with its existing local AI, tools, memory, STT/TTS and desktop workflows.

Never put API keys, memory files, reminders, or runtime logs into Git.
