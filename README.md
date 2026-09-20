# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

<!-- CI Windows build verification: 2026-09-20 -->

Target hardware:
- AMD Ryzen 5 2600 (6 cores / 12 threads)
- 16 GB RAM
- Radeon RX 570 4 GB
- Windows 10 x64

AI strategy:
- **JARVIS: главный гибридный мозг** — интернет-ИИ при наличии сети, локальный ИИ без сети
- **DeepSeek и GLM: дополнительные консультанты**, не главные
- Облачный ИИ используется только при наличии интернета
- Ollama is optional when exposed through its OpenAI-compatible API
- Model is replaceable; Jarvis is not tied to one runtime
- If `JARVIS_CHAT_MODEL` is empty, the OpenAI-compatible provider discovers the first model exposed by `/v1/models`

## Build jarvis.exe (Windows x64)

On your Windows PC, from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\build_exe.ps1
```

The build script installs the project with all Windows extras, runs the full unittest suite, and then creates `dist\\jarvis.exe`.

Result: `dist\\jarvis.exe` — single console exe, with the optional Windows audio and screenshot dependencies bundled.

GitHub Actions also builds the Windows executables on pushes and pull requests targeting `foundation`; the resulting package is uploaded as a workflow artifact.

## AI providers

JARVIS does not require a paid/cloud provider. The supported paths are:

### 1. JARVIS — основной режим (internet-first / offline fallback)

При наличии интернета JARVIS сначала обращается к настроенному OpenAI-compatible ИИ. Если интернет пропал, API недоступен или облачный лимит исчерпан, JARVIS автоматически переключается на встроенный локальный мозг llama.cpp + Qwen 3B. Возврат интернета автоматически возвращает облачный режим.

```powershell
$env:JARVIS_PROVIDER  = "openai-compatible"
$env:JARVIS_CHAT_URL  = "http://127.0.0.1:11434/v1/chat/completions"
$env:JARVIS_CHAT_KEY  = ""
$env:JARVIS_CHAT_MODEL = "your-local-model"
.\\dist\\jarvis.exe
```

`JARVIS_CHAT_MODEL` may be left empty when the local server exposes `/v1/models`; JARVIS will discover the first available model. The URL and model are configurable, so the same provider can work with compatible local runtimes such as Ollama, llama.cpp server, or LM Studio.

### 2. llama.cpp + Vulkan — direct local provider

```powershell
$env:JARVIS_PROVIDER = "local-vulkan"
$env:JARVIS_LLAMA_CLI = "llama-cli"
$env:JARVIS_MODEL = "model.gguf"
.\\dist\\jarvis.exe
```

This path runs the model locally and does not require an API key.

## Flutter UI (ui/)

```powershell
cd ui
flutter pub get
flutter run -d windows        # or: flutter build windows
```

The Flutter UI can spawn the agent through IPC. The native Windows desktop UI is `jarvis_desktop.py` and is packaged as `JARVIS-Desktop.exe` by CI.
Preview of the reactor animation without Flutter: open `ui/jarvis_reactor.html`.

## Android

The Android workflow generates the Flutter Android platform during CI and builds a standalone APK from `ui/`. The Android client connects directly to the configured OpenAI-compatible API; it is independent from the Windows process and does not use the Windows IPC channel.

## Release checklist

Before publishing a release, verify:
1. `git pull origin foundation`
2. `powershell -ExecutionPolicy Bypass -File scripts\\build_exe.ps1`
3. `dist\\jarvis.exe` starts and `/status`, `/calc`, `/now`, `/volume`, `/exit` work.
4. Verify the selected free/local AI provider and model through environment variables.
5. Run the Flutter UI smoke test if the UI is part of the release.
6. Test the **Jarvis wake word** and TTS interruption on a real Windows microphone. No clap activation is used.

Never put API keys, memory files, reminders, or runtime logs into Git.

## Память диалогов

- **Краткосрочная**: история сообщений (`chat_history`) сохраняется в `jarvis_memory.json`
  и восстанавливается при перезапуске. Ограничение — 40 обменов.
- **Долгосрочная**: заметки (`remember/recall`) и граф знаний (`kg_*`) — через инструменты.
- **RAG**: перед каждым вопросом в системный промпт автоматически подмешиваются
  релевантные заметки — модель «знает» факты без явного `/recall`.
- Очистка истории: `python -m agent --memory-clear`, кнопка очистки в UI,
  IPC-запрос {\"type\": \"clear_memory\"}.

## Голосовой режим

Основной режим активации JARVIS на desktop/CLI:

```powershell
poetry install --extras voice
$env:JARVIS_STT = "faster-whisper"
$env:JARVIS_TTS = "auto"
python -m agent --voice
```

JARVIS ожидает речь, но **не отправляет обычную речь в ядро**. Активация происходит только после слова **«Jarvis»** или **«Джарвис»**. Можно сказать «Jarvis, открой браузер» одной фразой. Если произнесено только «Jarvis», JARVIS активируется и ждёт следующую фразу. Хлопки и другие отдельные wake-сигналы не используются. Во время ответа начало речи останавливает TTS.

## Windows-полировка

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\install_autostart.ps1
powershell -ExecutionPolicy Bypass -File scripts\\install_autostart.ps1 -Remove
```
