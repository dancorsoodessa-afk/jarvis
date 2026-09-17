# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## Architecture

JARVIS uses one application core and one versioned client protocol. Windows Desktop, CLI, and Android are clients; transport is the only platform-specific layer.

```text
                 JARVIS CORE
                     |
        +------------+------------+
        |            |            |
      Windows      Android       CLI
        |            |            |
        +------------+------------+
                     |
              Protocol v1 (JSON)
                     |
          +----------+----------+
          |          |          |
        State       Tools     Memory
       Machine
```

The single state machine exposes: `idle`, `listening`, `thinking`, `executing`, `speaking`, `confirmation`, `error`, `exiting`. The 3D Reactor consumes these states and is therefore a live representation of the core rather than an unrelated animation.

## AI providers

- Free OpenAI-compatible provider — primary.
- Local llama.cpp + Vulkan provider.
- Ollama can be used through its OpenAI-compatible API.
- No paid provider is required.

## Windows

`JARVIS Desktop.exe` is the normal GUI package and is built without a console window. `JARVIS.exe` remains the core/CLI executable for development and IPC.

## Voice

Windows/desktop voice activation is **two claps -> speech -> JARVIS -> TTS -> standby**. The same voice engine owns microphone capture, VAD, STT and TTS interruption. Android keeps its separate device-native activation by saying **«Джарвис»**, then captures the command.

## Android / remote core

Android may connect directly to an OpenAI-compatible AI endpoint as a standalone mode, or to the real JARVIS core using the same Protocol v1 over TCP:

`tcp://WINDOWS_HOST:8765`

The Windows core can be started with:

```powershell
python -m agent --ipc-tcp 8765 0.0.0.0
```

Protocol messages are JSON lines with `protocol`, `id`, `type` and payload. Requests include `message`, `tool`, `tools`, `state`, `clear_memory`, and `ping`; asynchronous events include `state` and `delta`.

## Memory

Short-term conversation history is persisted and restored. Long-term notes, knowledge graph and RAG remain part of the core.

## Build

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The Windows build runs tests first and aborts before packaging when tests fail.
