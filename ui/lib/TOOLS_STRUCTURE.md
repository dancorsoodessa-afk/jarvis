# JARVIS tool/module layout

This repository keeps each tool implementation in its own feature module.

## Android / Flutter UI (`ui/lib/`)
- `crypto/`
  - `crypto_screen.dart` — visible crypto workspace/dashboard.
  - `crypto_tools.dart` — public market data and indicator calculations.
- `osint/`
  - `osint_screen.dart` — OSINT workspace.
  - `osint_tools.dart` — OSINT lookup helpers.
- `jarvis_client.dart` — AI/network client shared by the UI.
- `jarvis_reactor.dart` — animated core visualization.
- `main.dart` — application shell, navigation, voice lifecycle, settings and chat screen.

## Agent tools (`agent/tools/`)
- `apps.py` — app launching.
- `audio.py` — audio/volume.
- `clipboard.py` — clipboard.
- `files.py` — file operations.
- `osint.py` — OSINT actions.
- `processes.py` — process management.
- `registry.py` — tool registry.
- `screenshot.py` — screenshots.
- `system.py` — system information/actions.
- `ui_catalog.py` — UI/tool catalogue.
- `web.py` — web search.
- `agent/tools_catalog.py` — tool discovery/catalogue entry point.

## Rule for future changes
New tools must be added under a dedicated feature folder/module and exposed through the tool registry/navigation. Do not scatter tool implementation files in the UI root or mix a screen widget into a service file. Keep shared network/provider code in the AI client, and keep each feature's screen, data access, and tests together where practical.
