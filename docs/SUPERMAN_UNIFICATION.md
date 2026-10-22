# SUPERMAN — unification status

## Canonical project

- Repository: `dancorsoodessa-afk/jarvis`
- Working branch: `unified-superman`
- Integration PR: draft PR #32 against `foundation`
- ZEUS/ZEVS is explicitly out of scope.
- No old repositories, branches, archives, or local folders are deleted by this work.

## Selected components

- **Windows core:** the existing Python agent, tools, memory, task execution, and Tkinter desktop interface.
- **Desktop visual:** retain the existing animated neural-core interface and connect its state to the actual voice/network lifecycle.
- **Voice policy:** microphone capture, STT, and TTS are disabled without external HTTPS connectivity. Windows switches to text mode and restores voice when the connection returns. Android applies the same rule and stops native speech playback on disconnect.
- **Android client:** keep the existing Flutter UI and native Android adapter. Use the newer provider-fallback fixes, preserve configured OpenAI-compatible URLs, and keep regression tests.
- **AI providers:** OpenRouter is the default primary provider; Groq is the second provider, configured with a Qwen coding-capable model. Existing saved custom provider settings are preserved except known old default values that are migrated.
- **Android build:** use the verified Sherpa AAR dependency path rather than adding a duplicate JVM JAR; run Dart regression tests and APK checks in CI.

## Source audit decisions

- **JARVIS-ULTIMATE:** appears largely duplicated from the canonical JARVIS repository. Do not copy the repository wholesale; transplant only demonstrably unique, working changes.
- **NewRepo / PRIVATE prototype:** currently a small native Android skeleton with a basic AI client, settings store, and simple UI. It is not a complete verified assistant and does not replace the more developed Flutter client. Reuse any unique feature only after a source-level comparison.
- **Aetherial Network local folder:** the original local project folder has not yet been imported into this repository. The existing desktop neural interface is retained, but the original Three.js sphere and bundled visual assets still require inspection before migration.
- **PRIVATE v0.1/v0.2 archives:** their complete contents still need to be inspected before claiming that their features have been merged.

## Verification still required

1. Finish GitHub Actions for Windows tests/import and Android analysis/build/APK verification.
2. Test on the actual Windows PC: microphone permission/device, wake word, repeated commands, disconnect during listening/speaking, and reconnect.
3. Test on the actual Android phone: permission prompts, online/offline transitions, interruption of TTS, provider fallback, and APK installation/launch.
4. Inspect and import unique Aetherial/PRIVATE assets only after comparing their source and licensing.
5. Produce a release artifact named SUPERMAN and verify it on the target devices.
6. Keep all old projects until the new Windows and Android builds pass and the user confirms the merged product works. Only then consider archival/deletion with backups.

## Important distinction

The branch is an integration candidate, not a finished release. A green CI run verifies automated checks only; it does not prove that microphone hardware, spoken Russian, or the full Android runtime works on the user's devices.
