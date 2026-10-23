# JARVIS — Windows desktop assistant

JARVIS is a Python desktop assistant with a graphical interface, memory, OS tools, and a cloud language model.

## Architecture

- **Cloud LLM:** Hugging Face Inference Providers only.
- **Cloud speech recognition:** Hugging Face Router; requires `HF_TOKEN`.
- **Optional cloud speech output:** ElevenLabs; requires `ELEVENLABS_API_KEY`.
- **Local components:** desktop UI, microphone capture, memory files, and Windows automation tools. No local AI models are used.

## Build on Windows

From the repository root (the folder containing `pyproject.toml`, `jarvis_desktop.py`, and `agent/`):

```powershell
python -m pip install --upgrade pip
python -m pip install poetry
python -m poetry install --all-extras
python -m pip install "pyinstaller>=6.22,<7" pytest
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script runs the test suite before packaging. The executable is written to `release\JARVIS.exe`.

## Configure cloud access

Set a Hugging Face token in the current PowerShell session:

```powershell
$env:HF_TOKEN = "hf_your_token"
```

To persist it for future sessions, set the `HF_TOKEN` user environment variable in Windows Environment Variables, then restart JARVIS.

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

- An internet connection and a valid Hugging Face token are required for cloud chat.
- Cloud speech recognition requires the Hugging Face account to have access to the configured inference provider/model.
- Speech output remains disabled until an ElevenLabs key is configured; chat does not depend on TTS.
- Android is intentionally deferred; Android source is preserved for later work.
- Local operating-system utilities can still access files, processes, audio volume, and other desktop features. They are application tools, not local language models.
