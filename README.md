# JARVIS — Windows desktop assistant and Android client

JARVIS combines a Python agent core for Windows, a Flutter client for Android, local operating-system tools, memory, and cloud AI services.

## Architecture

- **Primary chat AI:** Google Gemini through its OpenAI-compatible endpoint.
- **Primary speech recognition:** Gemini cloud STT. When the key is missing or the quota is exhausted, voice input reports that it is unavailable instead of silently switching providers.
- **Optional local speech recognition:** Whisper can be enabled explicitly with `JARVIS_STT=local`; it is not an automatic fallback.
- **Speech output:** Gemini cloud TTS. No ElevenLabs or bundled offline voice engine is required.
- **3D interface:** Windows serves the real Three.js/WebGL reactor locally and embeds its Microsoft Edge app window into the main desktop window; Microsoft Edge must be installed. The Flutter Android client has its own animated reactor painter. CI covers embedding logic, but a real launch check on the target PC is still required before release.
- **Camera:** not implemented; JARVIS does not request camera access.

## Speech recognition modes

Gemini is the default speech-recognition engine and requires a valid API key and available quota. If the key is missing or the cloud quota is exhausted, JARVIS reports that voice input is unavailable instead of silently switching to another engine. To explicitly opt into local Whisper, set `JARVIS_STT=local`; it is not selected automatically after cloud errors.

## Configure cloud AI

1. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Open JARVIS → **Центр управления** and save the key under **GEMINI API KEY**.

4. Keep keys in the app's protected settings or environment variables. Never commit keys to Git.

Default chat/STT model: `gemini-3.5-flash-lite`. Gemini access and quotas depend on the API project; JARVIS reports API errors instead of pretending a failed request succeeded.

Environment variables used by the service include `GEMINI_API_KEY`, `JARVIS_CHAT_MODEL`, `JARVIS_STT_MODEL`, `JARVIS_GEMINI_TIMEOUT`, and `JARVIS_STT_TIMEOUT`.

## Build on Windows

```powershell
python -m pip install --upgrade pip
python -m pip install poetry
python -m pip install -e ".[all]"
python -m pip install "pyinstaller>=6.22,<7" pytest
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

The build script runs tests before packaging. The executable is written to `release\JARVIS.exe`. Do not distribute a release until CI tests, packaging, and a launch smoke test pass.

## Run from source

Prepare the pinned local Three.js engine once, then launch the Windows app:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_3d_assets.ps1
python -m agent
python jarvis_desktop.py
```

Android source and the release APK workflow are maintained under `ui/`. CI runs Dart analysis and Flutter tests before building the APK; verify the uploaded artifact and checksum before calling it ready.
