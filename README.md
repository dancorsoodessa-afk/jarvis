# JARVIS — Windows desktop assistant

JARVIS is a Windows desktop assistant with a graphical interface, memory, OS tools, and a cloud AI backend.

## Architecture

- **Primary cloud AI:** Google Gemini API using the official OpenAI-compatible endpoint.
- **Independent chat fallback:** Groq Cloud, configured with its own optional API key, model, timeout, and live endpoint check. If Groq is not configured, it is explicitly reported as unavailable.
- **Voice recognition:** microphone capture on the PC plus cloud Gemini transcription; requires internet and the Gemini API key.
- **Voice output:** cloud Gemini TTS with a configurable voice, model, and timeout.
- **3D interface:** real Three.js/WebGL neural reactor served locally and opened in the browser. The scene reacts to live microphone level and the assistant's listening, thinking, speaking, and error states.
- **Camera:** not implemented; JARVIS does not request camera access.

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

- Input: microphone audio is recorded locally and sent to Gemini for Russian transcription.
- Output: Gemini cloud TTS generates a WAV voice response using the same Gemini API key.
- Internet access is required for both cloud recognition and speech generation. If a service is unavailable, JARVIS reports the error rather than silently switching to a different voice engine.
- Configure the TTS model, voice, and request timeout in the control center.
- Check Windows microphone permissions and the selected input device if recording fails.

## Run from source

```powershell
python -m agent
python jarvis_desktop.py
```

Do not commit API keys to Git or paste them into source files. Android source is preserved for later work.
