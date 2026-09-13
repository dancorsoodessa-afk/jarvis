# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

Target hardware:
- AMD Ryzen 5 2600 (6 cores / 12 threads)
- 16 GB RAM
- Radeon RX 570 4 GB
- Windows 10 x64

AI strategy:
- **Free OpenAI-compatible provider: primary**
- **Local provider: llama.cpp + Vulkan**
- Paid/cloud provider integration is removed
- Ollama is optional when exposed through its OpenAI-compatible API
- Model is replaceable; Jarvis is not tied to one runtime

## Build jarvis.exe (Windows x64)

On your Windows PC, from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script installs the project with all Windows extras, runs the full unittest suite, and then creates `dist\jarvis.exe`.

Result: `dist\jarvis.exe` — single console exe, with the optional Windows audio and screenshot dependencies bundled.

GitHub Actions also builds the Windows executable on pushes and pull requests targeting `foundation`; the resulting `jarvis.exe` is uploaded as a workflow artifact.

## AI providers

JARVIS no longer contains a paid/cloud provider. The supported paths are:

### 1. OpenAI-compatible provider — default

Use any **free/local** service that exposes an OpenAI-compatible `/v1/chat/completions` endpoint. No paid API is required by JARVIS.

```powershell
$env:JARVIS_PROVIDER  = "openai-compatible"
$env:JARVIS_CHAT_URL  = "http://127.0.0.1:11434/v1/chat/completions"
$env:JARVIS_CHAT_KEY  = ""
$env:JARVIS_CHAT_MODEL = "your-local-model"
.\dist\jarvis.exe
```

The URL and model are configurable so the same provider can work with compatible local runtimes such as Ollama, llama.cpp server, or LM Studio.

### 2. llama.cpp + Vulkan — direct local provider

```powershell
$env:JARVIS_PROVIDER = "local-vulkan"
$env:JARVIS_LLAMA_CLI = "llama-cli"
$env:JARVIS_MODEL = "model.gguf"
.\dist\jarvis.exe
```

This path runs the model locally and does not require an API key.

## Flutter UI (ui/)

```powershell
cd ui
flutter pub get
flutter run -d windows        # or: flutter build windows
```

The UI spawns the agent itself: put `jarvis.exe` next to the UI binary,
or have Python on PATH (fallback: `python -m agent --ipc`).
Preview of the reactor animation without Flutter: open `ui/jarvis_reactor.html`.

## Release checklist

Before publishing a release, verify:
1. `git pull origin foundation`
2. `powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1`
3. `dist\jarvis.exe` starts and `/status`, `/calc`, `/now`, `/volume`, `/exit` work.
4. Verify the selected free/local AI provider and model through environment variables.
5. Run the Flutter UI smoke test if the UI is part of the release.

Never put API keys, memory files, reminders, or runtime logs into Git.

## Память диалогов

- **Краткосрочная**: история сообщений (`chat_history`) сохраняется в `jarvis_memory.json`
  и восстанавливается при перезапуске. Ограничение — 40 обменов.
- **Долгосрочная**: заметки (`remember/recall`) и граф знаний (`kg_*`) — через инструменты.
- **RAG**: перед каждым вопросом в системный промпт автоматически подмешиваются
  релевантные заметки — модель «знает» факты без явного `/recall`.
- Очистка истории: `python -m agent --memory-clear`, кнопка 🧹 в UI,
  IPC-запрос `{"type": "clear_memory"}`.

## Голосовой режим (wake word)

```powershell
poetry install --extras voice
$env:JARVIS_STT = "faster-whisper"
$env:JARVIS_TTS = "auto"
python -m agent --voice                # jarvis.exe --voice
```

Цикл: микрофон → STT → фильтр горячего слова «Джарвис» (`JARVIS_WAKE_WORD`,
отключается `JARVIS_WAKE=off`) → ответ агента → TTS. Запись ограничена
12 секундами с детекцией тишины.

## Windows-полировка

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Remove
```
