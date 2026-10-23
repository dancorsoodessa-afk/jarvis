# JARVIS architecture and release contract

Status: migration in progress. This document distinguishes the current implementation from the target architecture; it is not a claim that every target item is already implemented.

## Product boundaries

### Windows desktop
- `agent/` is the Python runtime: orchestration, provider access, memory, voice, tools, security and IPC.
- `jarvis_desktop.py` is the production Tkinter desktop shell and currently constructs the agent directly.
- `scripts/build_exe.ps1` is the authoritative Windows packaging entry point. It runs the Python test suite before packaging.
- `ui/jarvis_desktop.html` is a visual prototype, not the production Windows UI. It must not be advertised as integrated into the EXE until a tested host/bridge exists.

### Flutter UI and Android
- `ui/lib/main.dart` is the Flutter application entry point.
- `ui/lib/jarvis_client.dart` owns the Dart-side client contract: desktop IPC or standalone Android HTTP requests.
- `ui/android_main_activity.kt` is the current canonical Android activity source consumed by CI.
- `ui/android_tools/**` and `ui/crypto/**` are current native Kotlin source inputs copied into the generated Android project by CI.
- `.github/workflows/build-android.yml` generates the Flutter Android platform, stages the canonical Kotlin sources, downloads pinned voice artifacts, checks source contracts, runs Dart analysis, builds the arm64 release APK, verifies signature/alignment/package/permissions and uploads the APK with its manifest and SHA-256.
- `ui/android/**` is currently regenerated/deleted by the Android workflow. Files there are not authoritative source files. Do not implement fixes only in this directory.
- Top-level `app/src/**` is a legacy Android tree and is not the source used by the current Android workflow. Keep it out of release claims until it is either migrated or explicitly retired.

## AI provider contract

- The documented cloud AI provider is Hugging Face Inference API, using `https://router.huggingface.co/v1` as the OpenAI-compatible base URL.
- Android defaults and provider labels must match this contract. Do not silently fall back to unrelated OpenAI/Groq endpoints.
- A configured fallback model may be used only through the same documented provider endpoint and with an explicitly supplied token. Authentication failures must remain visible rather than being hidden by provider switching.
- Never commit API tokens, signing keys, private memory, or personal runtime logs.

## Release gates

### Android
1. CI must pass from the exact source commit being released.
2. Inspect job logs, not just the run badge.
3. Confirm APK exists, is signed, aligned, arm64-only, has expected package/version/permissions.
4. Preserve the artifact's SHA-256 and manifest.
5. A CI APK is build-verified, not device-verified. Microphone permission flow, Russian STT/TTS, wake/listen lifecycle, network calls and tool execution still require emulator/device smoke tests.

### Windows
1. Run `pytest tests/ -q` and desktop import checks on Windows.
2. Build the complete release folder/ZIP, including voice assets; do not distribute an EXE detached from required resources unless it is genuinely one-file packaged.
3. Run an executable smoke test and check startup, settings, microphone, TTS, IPC and shutdown.
4. The HTML prototype is not the Windows UI release until it is integrated and verified.

## Known architecture risks to resolve in order

1. **Source duplication:** legacy `app/src/**`, generated `ui/android/**`, and canonical Kotlin inputs under `ui/android_main_activity.kt` / `ui/android_tools/**` can be mistaken for interchangeable source. Keep changes on the canonical path and add checks that fail on accidental edits to generated copies.
2. **Different client contracts:** Windows uses Python agent IPC while Android uses a standalone Dart HTTP client plus Kotlin channels. Define shared request/response contracts and contract tests before trying to unify runtimes.
3. **Provider drift:** documentation, desktop defaults and mobile defaults must agree. The Android build now asserts the Hugging Face endpoint and rejects hard-coded OpenAI/Groq base URLs in `ui/lib/main.dart`.
4. **UI integration:** the new HTML neural interface is currently a prototype; production Tkinter remains the Windows shell. Integration requires a deliberate host/IPC decision and smoke tests, not merely copying the HTML file.
5. **Capability parity:** tools available on Android differ from tools in the Python agent. Publish a platform capability matrix and return explicit “unsupported on this platform” results instead of implying parity.
6. **Release evidence:** artifact names, commit SHA, package metadata and checksums must always refer to the same CI run. Never hand out an older artifact as a newly fixed build.

## Migration sequence

- Phase 1 — Stabilize builds and enforce the provider/source-of-truth contracts. Keep the work on the feature branch until CI is green.
- Phase 2 — Add tests for Dart client protocol, Android channel contracts, native tool safety and provider failover; run Android emulator smoke tests.
- Phase 3 — Resolve legacy Android tree ownership: migrate required code or mark/remove the obsolete tree only after dependency/use checks.
- Phase 4 — Separate platform-neutral product contracts from Windows and Android adapters; document and test capability differences.
- Phase 5 — Integrate the neural HTML interface into the actual Windows application behind a tested bridge, preserving existing voice, settings and tools.
- Phase 6 — Release only after Windows and Android build, test, package and smoke-test evidence is attached to the exact commit.

Do not mark a phase complete solely because its documentation exists. Mark it complete only after the listed checks pass.
