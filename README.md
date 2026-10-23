# JARVIS — Windows desktop assistant

JARVIS is a Windows desktop assistant with a graphical interface, memory, OS tools, and a cloud AI backend.

## Architecture

- **Cloud AI and coding:** Google Gemini API using Google's OpenAI-compatible endpoint.
- **Voice recognition:** Gemini audio understanding; it uses the same `GEMINI_API_KEY`.
- **Voice output:** Windows built-in System.Speech by default; no extra key or paid service required.
- **Local components:** UI, microphone capture, memory files, and Windows automation. No local LLM or STT model is downloaded.

## Get the free Gemini API key

1. Open [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create an API key for a project with Gemini API free-tier access.
3. Open JARVIS → **Центр управления** and paste the key into **GEMINI API KEY**.
4. Save and restart the core.

Alternatively, for the current PowerShell session:

```powershell
$env:GEMINI_API_KEY = "your_gemini_api_key"
```

Default model: `gemini-3.8-flash`. The free tier has model-specific rate limits and may change. Do not enable billing if you require strictly free usage. Free-tier requests may be subject to Google's data-use terms; review the current policy before sending sensitive data.

## Build on Windows

```powershell
python -m pip install --upgrade pip
python -m pip install poetry
python -m pip install -e ".[all]"
python -m pip install "pyinstaller>=6.22,<7" pytest
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script runs tests before packaging. The executable is written to `release\JARVIS.exe`.

## Voice

- Input: local microphone recording is sent to Gemini for transcription.
- Output: Windows' built-in speech engine by default.
- ElevenLabs is optional and not needed for normal voice operation.
- Check Windows microphone permissions if recording fails.

## Run from source

```powershell
python -m agent
python jarvis_desktop.py
```

Do not commit API keys to Git or paste them into source files. Android source is preserved for later work.
