# JARVIS — Windows desktop assistant

JARVIS is a Windows desktop assistant with a graphical interface, memory, OS tools, and a cloud AI backend.

## Architecture

- **Only chat provider:** the free consumer Gemini Web app at https://gemini.google.com/app, opened in the system browser.
- Windows and Android copy the current prompt to the clipboard; the user submits it in Gemini Web and copies the answer back into Jarvis.
- Gemini API model defaults and API-based STT/TTS are disabled. No Gemini API key or paid model is required for the web handoff.
- Jarvis local tools remain available in the desktop app, but AI responses are handled in Gemini Web rather than an API model.
- **3D interface:** real Three.js/WebGL neural reactor served locally and opened in the browser. The scene reacts to live microphone level and the assistant's listening, thinking, speaking, and error states.
- **Camera:** not implemented; JARVIS does not request camera access.

## Gemini Web companion (consumer app)

The Windows desktop composer and Android app's **Gemini Web** menu provide a handoff to the free consumer web app at https://gemini.google.com/app. Choose **Open Gemini Web and copy prompt**, paste it into Gemini Web, and submit it there. Copy Gemini's answer, then choose **Paste Gemini Web answer** to bring it back into Jarvis.

This is a user-mediated browser handoff, not an API integration: Gemini Web has its own Google-account session and quotas, and Jarvis cannot silently submit prompts, read private chat responses, or inherit the web app's login. Jarvis does not call a Gemini API model. Gemini Web responses are transferred manually through the clipboard. No Gemini Web password or session cookie is stored by Jarvis.

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

- Input: use the microphone inside Gemini Web; API-based speech recognition is disabled.
- Output: use Gemini Web's built-in voice features; API-based speech synthesis is disabled.
- Internet access is required to use Gemini Web.
- 
- Check Windows microphone permissions and the selected input device if recording fails.

## Run from source

Prepare the pinned local Three.js engine once, then launch the app:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_3d_assets.ps1
python -m agent
python jarvis_desktop.py
```

Do not commit API keys to Git or paste them into source files. Android source is preserved for later work.
