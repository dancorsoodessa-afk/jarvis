# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

Target hardware:
- AMD Ryzen 5 2600 (6 cores / 12 threads)
- 16 GB RAM
- Radeon RX 570 4 GB
- Windows 10 x64

AI strategy:
- Cloud provider: primary
- Local provider: llama.cpp + Vulkan
- Ollama: not required
- Model is replaceable; Jarvis is not tied to one runtime

Performance rule:
Never load a local model just because it exists. Local inference is opt-in and bounded.

## Build jarvis.exe (Windows x64)

On your Windows PC, from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script installs the project with all Windows extras, runs the full unittest suite, and then creates `dist\jarvis.exe`.

Result: `dist\jarvis.exe` — single console exe, with the optional Windows audio and screenshot dependencies bundled.

GitHub Actions also builds the Windows executable on pushes and pull requests targeting `foundation`; the resulting `jarvis.exe` is uploaded as a workflow artifact.

## Quick start: real cloud AI (OpenRouter)

OpenRouter provides an OpenAI-compatible chat-completions endpoint.

```powershell
$env:JARVIS_CLOUD_URL   = "https://openrouter.ai/api/v1/chat/completions"
$env:JARVIS_CLOUD_KEY   = "sk-or-v1-..."   # keep OUT of the repo!
$env:JARVIS_CLOUD_MODEL = "openai/gpt-5.3-chat"
$env:JARVIS_TTS         = "auto"           # voice on Windows (SAPI), no install
.\dist\jarvis.exe
```

Then just talk (no slash commands needed — the model can call tools itself):

> какая погода в Москве?  → Jarvis calls `weather`
> поставь громкость 30    → Jarvis calls `set_volume`
> найди все pdf на диске D → Jarvis calls `search`

Works with OpenAI-compatible endpoints such as OpenRouter, OpenAI, Groq,
local llama.cpp servers, and LM Studio. Change `JARVIS_CLOUD_URL`,
`JARVIS_CLOUD_KEY`, and `JARVIS_CLOUD_MODEL` without changing the code.

Voice via Piper (better quality):
```powershell
$env:JARVIS_TTS          = "piper"
$env:JARVIS_PIPER        = "C:\tools\piper\piper.exe"
$env:JARVIS_PIPER_VOICE  = "C:\tools\piper\voice\ru_RU-dmitri-medium.onnx"
```

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
4. Configure a fresh cloud API key through environment variables; never commit it.
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
poetry install --extras voice          # sounddevice + numpy
$env:JARVIS_STT = "faster-whisper"     # или whisper-cpp
$env:JARVIS_TTS  = "auto"
python -m agent --voice                # jarvis.exe --voice
```

Цикл: микрофон → STT → фильтр горячего слова «Джарвис» (`JARVIS_WAKE_WORD`,
отключается `JARVIS_WAKE=off`) → ответ агента → TTS. Запись ограничена
12 секундами с детекцией тишины.

## Windows-полировка

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1          # автозапуск при логине
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Remove  # убрать
```

