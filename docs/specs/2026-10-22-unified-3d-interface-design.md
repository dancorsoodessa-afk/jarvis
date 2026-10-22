# JARVIS Unified 3D Interface — Design Specification

Date: 2026-10-22
Target branch: `foundation`

## Goal
Replace the existing JARVIS visual presentation with one coherent, Russian-language, sci-fi dashboard for Windows and Android, matching the approved reference concept. Preserve working assistant capabilities and the Hugging Face Inference API provider configuration.

## Architecture
- Use one shared Three.js/WebGL scene packaged locally with the application; the visualization must not require a network connection.
- Embed the scene in the existing platform UI surfaces rather than replacing the Python/Flutter assistant backends.
- Keep platform-specific bridges thin: send runtime state and audio/activity measurements to the visual component; return only user interface actions through existing app interfaces.
- Do not load scripts, textures, fonts, or other visual assets from a CDN at runtime.

## Visual layout
- Center: animated 3D core with layered rotating rings, particles, glow and adaptive detail.
- Left panel: CPU, memory, GPU and disk readings only when real telemetry is available; unavailable readings must be labeled as unavailable rather than fabricated.
- Right panel: voice status, recent actions and quick commands backed by existing functions.
- Header: navigation, assistant status and settings.
- Bottom: command input and active model/provider status.
- Dark background, cyan/blue highlights, clear Russian labels, readable responsive layout.

## Runtime states
- Idle: slow, low-power core animation.
- Listening: driven by the real microphone/listening state; use input amplitude only where the platform exposes it.
- Processing: driven by actual request lifecycle events.
- Speaking: driven by real TTS playback state and audio level when available.
- Error/offline: clearly distinguish failures and unavailable services.
- Performance adaptation: reduce particles, post-processing and render resolution when frame time or device capability requires it.

## Compatibility and constraints
- Windows: preserve the current desktop shell, Python agent, voice pipeline and Hugging Face configuration.
- Android: preserve the current Flutter shell, native voice bridge and IPC/client behavior.
- No unrelated changes to crypto/recon modules, credentials, provider configuration, or assistant behavior.
- Keep the legacy visualization only until the new scene is integrated and verified; then remove superseded visual assets and references.
- Do not delete repositories, Git branches, unrelated files, or other JARVIS projects as part of this UI change without an explicit itemized deletion list.

## Verification
- Run Flutter formatting/analyzer/tests and available Windows/Python tests.
- Build Windows and Android where runners/toolchains permit.
- Verify local asset loading with network disabled.
- Verify all visual states are connected to real events, no fake telemetry is shown, and layout adapts to desktop and mobile.
- Report any platform build that could not be run instead of claiming it passed.

## Rollout
Implement on an isolated feature branch based on `foundation`, retain a rollback path, and merge only after tests/build checks and user review.