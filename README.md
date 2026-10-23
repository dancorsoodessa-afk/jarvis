# JARVIS — Windows desktop assistant

JARVIS is a Python desktop assistant with a graphical interface, memory, Windows tools, and a free-tier cloud AI backend.

## Architecture

- **Cloud LLM:** GroqCloud OpenAI-compatible API; no Hugging Face account or token.
- **Cloud speech recognition:** GroqCloud Whisper API, using the same key as chat.
- **Speech output:** Windows built-in System.Speech by default; no key or paid TTS service required. ElevenLabs remains optional.
- **Local components:** desktop UI, microphone capture, memory files, and Windows automation. No local language or speech-recognition model is downloaded.

## Set up the free cloud key

1. Create a free account at [GroqCloud Console](https://console.groq.com/).
2. Create an API key.
3. Open JARVIS → **Центр управления** and paste it into **GROQCLOUD API KEY**.
4. Save and restart the core.

Alternatively, set it for the current PowerShell session:

```powershell
$env:GROQ_API_KEY = "your_groq_api_key"
```

The default model is `openai/gpt-oss-20b`. Groq's free tier is rate-limited and limits can change. JARVIS does not silently switch to a paid endpoint if a quota is exhausted.

## Build on Windows

From the repository root (the folder containing `pyproject.toml`, `jarvis_desktop.py`, and `agent/`):

```powershell
python -m pip install --upgrade pip
python -m pip install poetry
python -m pip install -e ".[all]"
python -m pip install "pyinstaller>=6.22,<7" pytest
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script runs the test suite before packaging. The executable is written to `release\JARVIS.exe`.

## Voice

- Voice input uses the local microphone and sends audio to Groq Whisper.
- Voice output uses Windows' built-in speech engine by default.
- ElevenLabs is optional and not required for normal voice operation.
- If microphone access fails, check Windows microphone permissions and the selected input device.

## Run from source

```powershell
python -m agent
python jarvis_desktop.py
```

Do not commit API keys to Git or paste them into source files. Android source is preserved for later work.
