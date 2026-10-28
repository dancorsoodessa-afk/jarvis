# Architecture

JARVIS has a Python agent core, a Windows desktop interface, and a Flutter Android client.

```text
Windows Tk UI / Android Flutter UI
  -> Agent or IPC client
      -> Gemini API (primary chat + cloud STT/TTS)
      -> optional Groq API (chat fallback + Whisper STT fallback)
      -> ToolRegistry (local OS utilities; risky actions require confirmation)
      -> MemoryStore (local conversation and knowledge data)
```

## Cloud-only AI boundary

- Chat generation uses Google's Gemini OpenAI-compatible endpoint by default. The stable low-cost default model is `gemini-3.5-flash-lite`; availability still depends on the user's key, project and quota.
- Groq is optional. Its chat endpoint is used only when configured, and its speech-to-text endpoint is used as a reserve when `GROQ_API_KEY` is available.
- Speech recognition records microphone audio locally and transmits that file to a configured cloud provider. It does not bundle or load a local Whisper model.
- Speech synthesis uses Gemini cloud TTS. ElevenLabs is not part of the supported configuration.
- Local Python and Flutter code still runs on the device for UI, memory, microphone access, and OS tools. This is not a local LLM runtime.

## Configuration

- `GEMINI_API_KEY`: primary chat, transcription, and Gemini TTS key.
- `GROQ_API_KEY`: optional independent chat and speech-recognition fallback.
- `JARVIS_CHAT_MODEL`: optional primary chat model.
- `JARVIS_STT_MODEL`: optional primary Gemini STT model.
- `JARVIS_STT_FALLBACK_MODEL`: optional Groq STT model; defaults to `whisper-large-v3-turbo`.
- `JARVIS_GEMINI_TIMEOUT`, `JARVIS_STT_TIMEOUT`: bounded API timeouts.

Quota exhaustion is not treated as transient: the same Gemini STT request is not retried when a provider response indicates that the daily/free-tier quota has been exhausted. The configured Groq STT fallback is attempted once. Without a reserve provider, the error is surfaced clearly and text chat remains available.

## Interface status

The Windows app currently serves the true Three.js/WebGL reactor locally and opens it in a browser. It is not yet embedded into the Tkinter main window; this remains an explicit outstanding item in issue #43. The Android client currently uses an animated Flutter painter for its reactor. These implementations must not be described as a unified single-window Three.js interface until that work and its smoke tests are complete.

## IPC

The optional IPC protocol is JSON Lines over stdin/stdout. Keep the transport local. Risky tools must continue to require confirmation.
