# JARVIS Cloud Voice and 3D Interface — Architecture Specification

Date: 2026-10-24
Target branch: `foundation`

## Goal
Replace the Windows desktop's pseudo-3D Canvas orb with a real Three.js/WebGL reactor, use cloud speech recognition and expressive cloud speech synthesis, and provide an independent chat-provider fallback. Keep camera functionality out of scope.

## Architecture
- Primary chat provider: Google Gemini API.
- Optional independent chat fallback: Groq Cloud, with its own API key, model ID, timeout, endpoint health check, and visible status. It must not be presented as a separate provider when no Groq key is configured.
- Speech recognition: cloud Gemini transcription with a dedicated model setting, request timeout, startup reachability check, and visible error status.
- Speech synthesis: cloud Gemini TTS with dedicated voice, model, request timeout, and startup reachability check. Do not use a local Windows speech engine or any third-party TTS service.
- The Three.js scene is served from a loopback-only local HTTP server. The pinned engine modules are bundled with the application; the scene must not load scripts, textures, fonts, or other assets from a CDN at runtime.
- The camera is deferred. Do not request camera permissions, initialize video devices, or register face-detection tools.
- Keep the Python assistant backend, tool execution, memory, settings, and confirmation flow intact.

## 3D scene
- Center: animated 3D neural reactor with a deforming icosahedral core, layered rotating rings, particles, glow, and depth.
- Use the real Three.js/WebGL renderer; do not simulate the central reactor with Tkinter Canvas primitives.
- Idle: low-intensity slow animation.
- Listening: use measured microphone amplitude while the voice capture loop is active.
- Processing: use actual request lifecycle events.
- Speaking: use the real cloud TTS playback lifecycle.
- Error/offline: display a distinct error color and status.
- Adapt pixel ratio and visual intensity to avoid excessive GPU usage.
- The current Windows implementation opens the 3D scene in the system browser and synchronizes state over loopback HTTP. The Tkinter chat/controls remain the assistant shell.

## Provider behavior
- Gemini and Groq must use independent keys, model IDs, timeouts, health checks, and status labels.
- The router tries the configured Gemini role/model first and may use Groq only after a real Gemini failure. It must not retry the same failed Gemini endpoint through multiple role profiles.
- Provider availability is a live check, not inferred from successful local agent construction.
- STT and TTS require internet access. When the cloud service fails, surface a specific error instead of silently switching to a different voice engine.
- API keys must be protected in saved settings and must never be committed to source.

## Verification
- Run the Python test suite, desktop import check, and compile check.
- Verify local scene and engine assets are bundled in the EXE and can be served without a CDN.
- Verify provider health checks, timeout handling, missing-key behavior, Groq fallback, and TTS response decoding.
- Verify that the scene responds to microphone amplitude, request state, and actual playback completion.
- Build the Windows EXE in CI. Do not claim that hardware-specific microphone or speaker playback has been verified without testing on the target PC.
- Android remains a separate follow-up; this specification does not claim that the Windows 3D scene has been integrated into the Android application.
