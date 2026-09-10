# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

## Особенности и улучшения

### Безопасность
- Фильтрация чувствительных данных в логах (API keys, пароли, пути к файлам)
- Улучшенная система подтверждения действий для предотвращения случайного выполнения опасных операций
- Защита от атак типа division by zero в математических вычислениях
- Валидация входных данных для всех инструментов

### Надежность
- Устойчивое к повреждениям хранилище памяти и настроек
- Автоматическое создание недостающих директорий
- Обработка ошибок JSON-файлов без падения агента
- Резервное копирование важных данных

### Функциональность
- Математический вычислитель с поддержанием сложных выражений
- Система напоминаний с гибкой настройкой времени
- База знаний для сохранения важной информации
- Интеграция с различными AI провайдерами (облачные и локальные)

## Target hardware:

- AMD Ryzen 5 2600 (6 cores / 12 threads)
- 16 GB RAM
- Radeon RX 570 4 GB
- Windows 10 x64

## AI strategy:

- Cloud provider: primary
- Local provider: llama.cpp + Vulkan
- Ollama: not required
- Model is replaceable; Jarvis is not tied to one runtime

## Performance rule:

Never load a local model just because it exists. Local inference is opt-in and bounded.

## Build jarvis.exe (Windows x64)

On your Windows PC, from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Result: `dist\jarvis.exe` — single console exe, no Python needed on the machine.

Or let GitHub build it: the workflow in `.github/workflows/build-exe.yml`
runs tests and produces `jarvis.exe` as a downloadable artifact on every push.

Configuration via environment variables (see agent/config.py):
`JARVIS_LOCAL`, `JARVIS_CLOUD_URL`, `JARVIS_LLAMA_CLI`, `JARVIS_MODEL`, ...

## Quick start: real cloud AI (OpenAI-compatible)

```powershell
$env:JARVIS_CLOUD_URL   = "https://api.openai.com/v1/chat/completions"
$env:JARVIS_CLOUD_KEY   = "sk-..."        # keep OUT of the repo!
$env:JARVIS_CLOUD_MODEL = "gpt-4o-mini"
$env:JARVIS_TTS         = "auto"          # voice on Windows (SAPI), no install
jarvis
```

Then just talk (no slash commands needed — the model picks tools itself):

> какая погода в Москве?  → Jarvis calls `weather`
> поставь громкость 30    → Jarvis calls `set_volume`
> найди все pdf на диске D → Jarvis calls `search`

Works with any OpenAI-compatible endpoint: OpenRouter, Groq,
local llama.cpp server (`--server`), LM Studio, etc.

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

## Recent Improvements

### Security Enhancements
- Sensitive data filtering in logs to prevent accidental disclosure of API keys, passwords, etc.
- Input validation for all tools to prevent injection attacks
- Confirmation system for dangerous operations to prevent accidental execution

### Reliability Improvements
- Robust JSON handling with automatic recovery from corrupted files
- Directory creation for data files to prevent path-related errors
- Graceful degradation when external services are unavailable

### Mathematical Safety
- Division by zero protection in the calculator
- Overflow protection for large numbers
- Input sanitization to prevent code injection

## Development

This project is under active development. Contributions are welcome!

### Running Tests

To run the test suite:

```powershell
python -m unittest discover -s tests
```

### Code Style

Please follow the existing code style in the project when making contributions.