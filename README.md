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


## Быстрый старт для Windows

Если нужен обычный графический JARVIS, **не запускай \`jarvis.exe\` вручную**. Основной интерфейс — \`JARVIS Desktop.exe\`.

### Вариант A — готовый Windows-пакет

1. Скачай артефакт \`JARVIS-Windows-x64\` из GitHub Actions.
2. Распакуй весь пакет в одну папку. **Не вытаскивай только один EXE:** рядом должны находиться \`piper\\\` и остальные файлы пакета.
3. Запусти **\`JARVIS Desktop.exe\`**.
4. Настрой провайдера ИИ и голос в окне настроек.
5. Ключи API храни в настройках/переменных окружения и **не добавляй их в Git**.

Готовый пакет содержит два EXE:
- \`JARVIS Desktop.exe\` — основной графический интерфейс.
- \`JARVIS.exe\` — ядро/CLI.

### Вариант B — запуск из исходников

Требуется Windows x64, Python и зависимости проекта:

~~~
powershell -ExecutionPolicy Bypass -File scripts\\build_exe.ps1
.\\release\\JARVIS Desktop.exe
~~~

После сборки папка \`release\\\` является готовым комплектом. Скрипт сборки также создаёт \`JARVIS-Windows-x64.zip\`.

### Flutter UI

Для разработки Flutter-интерфейса:

~~~
cd ui
flutter pub get
flutter run -d windows
~~~

Для release-сборки:

~~~
flutter build windows
~~~

Flutter UI может запускать агент через IPC. Если готового Windows EXE нет, **Flutter сам по себе не заменяет Python-ядро**: для полной работы агента нужен собранный JARVIS или доступный Python-окружению backend/IPC-процесс. В обычной готовой Windows-установке используй \`JARVIS Desktop.exe\` из папки \`release\\\`.

## Переменные окружения

Все основные runtime-настройки читаются из \`agent/config.py\`. Ниже указаны фактические имена, значения по умолчанию и назначение.

| Переменная | Описание | По умолчанию | Обязательна |
|---|---|---|---|
| \`JARVIS_PROVIDER\` | Провайдер: \`openai-compatible\` или \`local-vulkan\` | \`openai-compatible\` | Нет |
| \`JARVIS_CHAT_URL\` | URL OpenAI-compatible API | пусто | Для cloud/local API — да |
| \`JARVIS_CHAT_KEY\` | API-ключ провайдера | пусто | Зависит от API |
| \`JARVIS_CHAT_MODEL\` | Имя модели | \`openrouter/free\` | Нет |
| \`JARVIS_DEEPSEEK_URL\` | URL дополнительного DeepSeek-провайдера | пусто | Нет |
| \`JARVIS_DEEPSEEK_KEY\` | Ключ DeepSeek | пусто | Нет |
| \`JARVIS_DEEPSEEK_MODEL\` | Модель DeepSeek | \`deepseek/deepseek-chat:free\` | Нет |
| \`JARVIS_GLM_URL\` | URL дополнительного GLM-провайдера | пусто | Нет |
| \`JARVIS_GLM_KEY\` | Ключ GLM | пусто | Нет |
| \`JARVIS_GLM_MODEL\` | Модель GLM | \`z-ai/glm-5.2:free\` | Нет |
| \`JARVIS_LLAMA_CLI\` | Исполняемый файл llama.cpp | \`llama-cli\` | Только local-vulkan |
| \`JARVIS_MODEL\` | Путь к GGUF-модели для local-vulkan | \`model.gguf\` | Только local-vulkan |
| \`JARVIS_CTX\` | Размер контекста, минимум 256 | \`2048\` | Нет |
| \`JARVIS_THREADS\` | Число CPU-потоков, минимум 1 | \`6\` | Нет |
| \`JARVIS_MEMORY\` | Файл краткосрочной памяти | \`jarvis_memory.json\` | Нет |
| \`JARVIS_KG\` | Файл графа знаний | пусто | Нет |
| \`JARVIS_LOCAL\` | Если равно \`1\`, принудительно включает local-vulkan | пусто | Нет |

### Примеры конфигурации

**OpenAI-compatible API:**

~~~
$env:JARVIS_PROVIDER = "openai-compatible"
$env:JARVIS_CHAT_URL = "https://your-provider.example/v1/chat/completions"
$env:JARVIS_CHAT_KEY = "YOUR_API_KEY"
$env:JARVIS_CHAT_MODEL = "your-model"
.\\release\\JARVIS.exe
~~~

**Полностью локальный llama.cpp:**

~~~
$env:JARVIS_PROVIDER = "local-vulkan"
$env:JARVIS_LLAMA_CLI = "llama-cli"
$env:JARVIS_MODEL = "C:\\Models\\model.gguf"
.\\release\\JARVIS.exe
~~~

## Troubleshooting

### \`JARVIS Desktop.exe\` не запускается

- Распакуй **весь** Windows-пакет, а не только EXE.
- Проверь, что рядом с EXE присутствует папка \`piper\\\`.
- Попробуй запустить EXE из PowerShell, чтобы увидеть текст ошибки:

~~~
cd "C:\\путь\\к\\JARVIS"
.\\JARVIS Desktop.exe
~~~

- Если Windows Defender показывает предупреждение для самособранного EXE, проверь источник пакета и подпись/хэш файла перед разрешением запуска. Не отключай Defender целиком.

### ИИ не отвечает

- Проверь \`JARVIS_CHAT_URL\`, \`JARVIS_CHAT_KEY\` и \`JARVIS_CHAT_MODEL\`.
- Для локального API проверь, что сервер действительно запущен и открывает \`/v1/models\`.
- Если \`JARVIS_CHAT_MODEL\` пустой, JARVIS пытается выбрать первую модель из \`/v1/models\`.
- При использовании \`local-vulkan\` проверь \`llama-cli\` и путь к GGUF-модели.

### Нет голоса / ошибка TTS

- Для исходников установи голосовые зависимости: \`poetry install --extras voice\`.
- Для готового Windows-пакета проверь наличие \`piper\\piper.exe\` и русской модели Dmitri.
- Проверь настройки TTS и микрофона в JARVIS.

### Не работает микрофон / wake word

- Разреши приложению доступ к микрофону в Windows.
- Говори **«Jarvis»** или **«Джарвис»**. Обычная речь до wake word не отправляется в ядро.
- Хлопки и отдельные clap-сигналы не являются wake word.

### Память не сохраняется

- Проверь права записи в каталог, где находится \`jarvis_memory.json\`, либо заданный \`JARVIS_MEMORY\`.
- Не удаляй файл памяти во время работы JARVIS.
- Для очистки истории используй \`python -m agent --memory-clear\` или кнопку очистки в UI.

### Windows пишет, что не найден Python/.NET

Для **готового PyInstaller-пакета** Python и .NET не нужны для запуска JARVIS. Если запускаешь проект из исходников, установи зависимости проекта и используй команды из разделов Quick Start/Voice. Ошибка о Python обычно означает, что запущен исходный скрипт, а не готовый EXE.

## Полезные команды PowerShell для новичков

Показать текущую папку:

~~~
Get-Location
~~~

Перейти в папку JARVIS:

~~~
cd "C:\\путь\\к\\jarvis"
~~~

Посмотреть содержимое:

~~~
Get-ChildItem
~~~

Запустить Desktop:

~~~
.\\JARVIS Desktop.exe
~~~

Проверить, что EXE существует:

~~~
Test-Path ".\\JARVIS Desktop.exe"
~~~

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

Основной режим: локальный `faster-whisper small` для распознавания и локальный `Piper + Dmitri Medium` для озвучивания. Облачные TTS в JARVIS не используются.

Основной режим активации JARVIS на desktop/CLI:

```powershell
poetry install --extras voice
$env:JARVIS_STT = "faster-whisper"
$env:JARVIS_TTS = "piper"
python -m agent --voice
```

JARVIS ожидает речь, но **не отправляет обычную речь в ядро**. Активация происходит только после слова **«Jarvis»** или **«Джарвис»**. Можно сказать «Jarvis, открой браузер» одной фразой. Если произнесено только «Jarvis», JARVIS активируется и ждёт следующую фразу. Хлопки и другие отдельные wake-сигналы не используются. Во время ответа начало речи останавливает TTS.

## Windows-полировка

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\install_autostart.ps1
powershell -ExecutionPolicy Bypass -File scripts\\install_autostart.ps1 -Remove
```
