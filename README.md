# JARVIS — Windows desktop assistant

JARVIS is a Python desktop assistant with a graphical interface, memory, OS tools, and a cloud language model.

## Architecture

- **Cloud LLM:** Google Gemini API through its OpenAI-compatible endpoint.
- **Cloud speech recognition:** Google Gemini API; requires `GEMINI_API_KEY`.
- **Optional cloud speech output:** ElevenLabs; requires `ELEVENLABS_API_KEY`.
- **Local components:** desktop UI, microphone capture, memory files, and Windows automation tools. No local AI model is required.

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

## Configure cloud access

Create an API key in [Google AI Studio](https://aistudio.google.com/apikey), then set it in the current PowerShell session:

```powershell
$env:GEMINI_API_KEY = "your_gemini_api_key"
```

To persist it for future sessions, set the `GEMINI_API_KEY` user environment variable in Windows Environment Variables, then restart JARVIS. You may override the model with `JARVIS_CHAT_MODEL`; the default is `gemini-2.5-flash`.

Optional cloud speech output:

```powershell
$env:ELEVENLABS_API_KEY = "your_elevenlabs_key"
```

Do not commit API tokens to Git or paste them into source files.

## Run from source

```powershell
python -m agent
```

For the desktop UI, run `python jarvis_desktop.py`.

## Notes

- An internet connection and a valid Gemini API key are required for cloud chat.
- Gemini API quotas and free-tier availability depend on account, region, and current provider terms.
- Android uses the Gemini OpenAI-compatible API endpoint as well; its API key is entered in the Android app settings.
- Local operating-system utilities can still access files, processes, audio volume, and other Windows features. They are application tools, not local language models.
