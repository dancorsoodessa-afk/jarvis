# Architecture

JARVIS is a Windows desktop application with a Python agent core.

```text
Desktop UI (jarvis_desktop.py)
  -> Agent Core (agent/)
      -> Hugging Face Inference Providers (cloud LLM; internet required)
      -> ToolRegistry (local OS utilities, with confirmation for risky actions)
      -> MemoryStore (local conversation and knowledge data)
      -> Cloud STT (Hugging Face; microphone capture is local)
      -> Optional cloud TTS (ElevenLabs)
```

## Cloud-only AI boundary

- Chat generation is restricted to `https://router.huggingface.co/v1/chat/completions`.
- Local LLM runtimes and model discovery on localhost are not supported.
- Speech recognition uses the Hugging Face cloud endpoint; no Whisper model is bundled or loaded locally.
- Speech synthesis is optional and uses ElevenLabs when configured; no Piper executable or voice model is bundled.
- Local Python code remains necessary for the desktop UI, memory, microphone capture, and operating-system tools. These are not local AI models.

## Configuration

- `HF_TOKEN`: Hugging Face access token for chat and cloud STT.
- `JARVIS_CHAT_MODEL`: optional chat model slug.
- `JARVIS_STT_URL`: optional Hugging Face Router speech-recognition URL.
- `ELEVENLABS_API_KEY` or `JARVIS_ELEVENLABS_API_KEY`: optional cloud TTS key.

## IPC

The optional IPC protocol is JSON Lines over stdin/stdout or TCP. Keep the transport local unless remote access is explicitly secured. Risky tools must continue to require confirmation.
