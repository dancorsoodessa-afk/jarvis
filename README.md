# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## AI strategy

JARVIS uses a replaceable local AI architecture:
- **OpenAI-compatible local provider** for Ollama, llama.cpp server, LM Studio and similar runtimes.
- **llama.cpp + Vulkan** for direct local GGUF inference.
- **AirLLM** as an optional direct Python provider for very large Hugging Face models on limited VRAM.

AirLLM is deliberately optional and is not installed by the normal Windows build. Install the dedicated extra only when you want it:

```powershell
poetry install --extras airllm
```

Then select it:

```powershell
$env:JARVIS_PROVIDER = "airllm"
$env:JARVIS_AIRLLM_MODEL = "Qwen/Qwen3-8B"
python -m agent
```

AirLLM loads lazily on the first AI request. If the package or model is unavailable, JARVIS reports the concrete error instead of failing during startup.

## Safety model

Tools are registered explicitly. Destructive actions such as deleting files, killing processes, launching applications, and sending email require explicit confirmation. Tool errors are caught and returned to the agent rather than crashing the process.

The project keeps the human operator out of manual source editing: changes are made through the development branch, tests are run, and Windows packaging is verified before release.

## Build jarvis.exe (Windows x64)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script installs the project with the normal Windows extras, runs the full unittest suite, and creates `dist\jarvis.exe`.

## Local OpenAI-compatible provider

```powershell
$env:JARVIS_PROVIDER  = "openai-compatible"
$env:JARVIS_CHAT_URL  = "http://127.0.0.1:11434/v1/chat/completions"
$env:JARVIS_CHAT_KEY  = ""
$env:JARVIS_CHAT_MODEL = "your-local-model"
python -m agent
```

The endpoint can also be auto-discovered from a list of common local OpenAI-compatible servers.

## Direct llama.cpp + Vulkan

```powershell
$env:JARVIS_PROVIDER = "local-vulkan"
$env:JARVIS_LLAMA_CLI = "llama-cli"
$env:JARVIS_MODEL = "model.gguf"
python -m agent
```

## Memory

- Short-term dialog history is persisted in `jarvis_memory.json`.
- Long-term notes use `remember` / `recall`.
- A knowledge graph stores explicit relations.
- Relevant notes can be injected into the local OpenAI-compatible system prompt.

## Russian voice

The voice stack supports local STT through `faster-whisper` or `whisper.cpp` and a local TTS layer. The STT module explicitly requests Russian (`ru`) and never performs network requests itself.

```powershell
poetry install --extras voice
$env:JARVIS_STT = "faster-whisper"
python -m agent --voice
```

## Verification

The repository contains tests for the agent, memory, IPC, security confirmation, tools, STT, backend discovery, and AirLLM integration. The `foundation` branch remains the release baseline; development work is performed on dedicated branches first.
