# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

<!-- CI Windows build verification: 2026-09-20 -->

Target hardware:
- AMD Ryzen 5 2600 (6 cores / 12 threads)
- 16 GB RAM
- Radeon RX 570 4 GB
- Windows 10 x64

AI strategy:
- **JARVIS: Hugging Face Inference API** — облачный ИИ через единый Hugging Face токен
- **Используется только Hugging Face Inference API**
- Облачный ИИ используется только при наличии интернета
- Model is replaceable; Jarvis is not tied to one runtime
- Все облачные запросы принудительно направляются на `https://router.huggingface.co/v1/chat/completions`

## Build jarvis.exe (Windows x64)

On your Windows PC, from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\build_exe.ps1
```

The build script installs the project with all Windows extras, runs the full unittest suite, and then creates `dist\\jarvis.exe`.

Result: `dist\\jarvis.exe` — single console exe, with the optional Windows audio and screenshot dependencies bundled.

GitHub Actions also builds the Windows executables on pushes and pull requests targeting `foundation`; the resulting package is uploaded as a workflow artifact.


## Быстрый старт для Windows

Текущая Windows-сборка — однофайловое графическое приложение `release/JARVIS.exe`, создаваемое из `jarvis_desktop.py`. Отдельные `JARVIS Desktop.exe` и CLI EXE текущий workflow не выпускает.

### Вариант A — готовый Windows-пакет

1. Скачай артефакт `JARVIS-Windows-x64` из GitHub Actions.
2. Сохрани EXE на диск и запусти `JARVIS.exe`.
3. Настрой Hugging Face token и модель в приложении или через переменные окружения.
4. Не добавляй токены, память и runtime-логи в Git.

Это one-file сборка: обязательные ресурсы STT/TTS встраиваются в EXE. Отдельная папка Piper для запуска релизного файла не требуется.

### Вариант B — сборка из исходников

Требуется Windows x64 и Python 3.12:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\build_exe.ps1
.\\release\\JARVIS.exe
```

Скрипт запускает тесты, загружает ресурсы STT/TTS и создаёт однофайловый EXE в `release/`.

### Flutter UI

Для разработки Flutter-интерфейса:

```powershell
cd ui
flutter pub get
flutter run -d windows
```

Для release-сборки: `flutter build windows`.

Flutter UI может запускать Python-агент через IPC. HTML-файл `ui/jarvis_desktop.html` пока является прототипом нейронного интерфейса и не встроен в текущий Windows EXE. Не считать визуальный прототип частью релиза до интеграции и smoke-тестирования.

## Переменные окружения

Все основные runtime-настройки читаются из \`agent/config.py\`. Ниже указаны фактические имена, значения по умолчанию и назначение.

| Переменная | Описание | По умолчанию | Обязательна |
|---|---|---|---|
| \`JARVIS_PROVIDER\` | AI-провайдер (зафиксирован на Hugging Face) | \`huggingface\` | Нет |
| \`JARVIS_CHAT_URL\` | Игнорируется: endpoint зафиксирован на Hugging Face | Hugging Face endpoint | Нет |
| \`HF_TOKEN\` | Hugging Face access token | пусто | Да |
| \`JARVIS_CHAT_MODEL\` | Имя модели | \`Qwen/Qwen2.5-7B-Instruct-1M\` | Нет |
| \`JARVIS_CTX\` | Размер контекста, минимум 256 | \`2048\` | Нет |
| \`JARVIS_THREADS\` | Число CPU-потоков, минимум 1 | \`6\` | Нет |
| \`JARVIS_MEMORY\` | Файл краткосрочной памяти | \`jarvis_memory.json\` | Нет |
| \`JARVIS_KG\` | Файл графа знаний | пусто | Нет |

### Примеры конфигурации

**Hugging Face Inference API:**

~~~
$env:JARVIS_PROVIDER = "huggingface"
$env:JARVIS_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
$env:HF_TOKEN = "hf_ВАШ_ТОКЕН"
$env:JARVIS_CHAT_MODEL = "your-model"
.\\release\\JARVIS.exe
~~~

## Troubleshooting

### `JARVIS.exe` не запускается

- Запусти EXE из PowerShell, чтобы увидеть системную ошибку:
  
```powershell
cd "C:\\путь\\к\\JARVIS"
.\\JARVIS.exe
```

- Проверь, что скачан полный артефакт из GitHub Actions, а Windows Defender не поместил файл в карантин.
- Перед запуском проверь источник и SHA-256 опубликованного файла. Не отключай Defender целиком.

### ИИ не отвечает

- Проверь `HF_TOKEN` или сохранённый `JARVIS_CHAT_KEY`.
- Проверь `JARVIS_CHAT_MODEL` и доступность модели в Hugging Face Inference Providers.
- Endpoint фиксирован на `https://router.huggingface.co/v1/chat/completions`; `JARVIS_CHAT_URL` его не переопределяет.
- HTTP 401/403 обычно указывает на токен или права модели; HTTP 429 — на лимит запросов.

### Нет голоса / ошибка TTS

- Для исходников установи голосовые зависимости: `poetry install --extras voice`.
- В one-file EXE Piper и русская модель Dmitri встраиваются в приложение; отдельная папка `piper/` не требуется.
- Проверь разрешение микрофона, устройство ввода и настройки голоса в Windows.

### Не работает wake word

- Разреши приложению доступ к микрофону в Windows.
- Говори **«Jarvis»** или **«Джарвис»**. Обычная речь до wake word не отправляется в ядро.
- Хлопки и отдельные clap-сигналы не используются как wake word.

### Память не сохраняется

- Проверь права записи в каталог, где находится `jarvis_memory.json`, либо заданный `JARVIS_MEMORY`.
- Не удаляй файл памяти во время работы JARVIS.
- Для очистки истории используй `python -m agent --memory-clear`, кнопку очистки в UI или IPC-запрос `{"type": "clear_memory"}`.

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

## AI provider — Hugging Face only

JARVIS uses only Hugging Face Inference API for cloud AI. OpenRouter, direct DeepSeek/GLM endpoints, custom provider URLs, and local AI provider selection are not supported by the runtime.

```powershell
$env:JARVIS_PROVIDER = "huggingface"
$env:HF_TOKEN = "hf_ВАШ_ТОКЕН"
$env:JARVIS_CHAT_MODEL = "Qwen/Qwen2.5-7B-Instruct-1M"
.\\release\\JARVIS.exe
```

The endpoint is fixed to `https://router.huggingface.co/v1/chat/completions`. Use a model ID available through Hugging Face Inference Providers.

## Flutter UI (ui/)

```powershell
cd ui
flutter pub get
flutter run -d windows        # or: flutter build windows
```

The Flutter UI can spawn the Python agent through IPC on desktop. The current Windows release is built from `jarvis_desktop.py` as a single-file `release/JARVIS.exe`; the HTML neural interface remains a prototype and is not integrated into that EXE.
Preview of the reactor animation without Flutter: open `ui/jarvis_reactor.html`.

## Android

The Android workflow generates the Flutter Android platform during CI and builds a standalone APK from `ui/`. The Android client connects to Hugging Face Inference API; it is independent from the Windows process and does not use the Windows IPC channel.

## Release checklist

Before publishing a release, verify:
1. `git pull origin foundation`
2. `powershell -ExecutionPolicy Bypass -File scripts\\build_exe.ps1`
3. `dist\\jarvis.exe` starts and `/status`, `/calc`, `/now`, `/volume`, `/exit` work.
4. Verify the Hugging Face token and model ID through environment variables.
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
