# JARVIS

Personal AI Agent / Desktop Assistant for Windows x64.

Target hardware:
- AMD Ryzen 5 2600 (6 cores / 12 threads)
- 16 GB RAM
- Radeon RX 570 4 GB
- Windows 10 x64

AI strategy:
- Cloud provider: primary
- Local provider: llama.cpp + Vulkan
- Ollama: not required
- Model is replaceable; Jarvis is not tied to one runtime

Performance rule:
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

## Flutter UI (ui/)

```powershell
cd ui
flutter pub get
flutter run -d windows        # or: flutter build windows
```

The UI spawns the agent itself: put `jarvis.exe` next to the UI binary,
or have Python on PATH (fallback: `python -m agent --ipc`).
Preview of the reactor animation without Flutter: open `ui/jarvis_reactor.html`.
