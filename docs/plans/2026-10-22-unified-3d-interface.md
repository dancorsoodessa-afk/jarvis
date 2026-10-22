# JARVIS Unified 3D Interface Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current JARVIS visual presentation on Windows and Android with a responsive, locally packaged Three.js 3D dashboard while preserving existing assistant behavior.

**Architecture:** Keep the Python desktop agent and Flutter/Android assistant as the owners of their existing runtime and voice states. Introduce a shared local HTML/JavaScript visualization and small platform adapters that pass explicit state updates into the scene. The scene must not invent telemetry or load remote assets.

**Tech Stack:** Python/Tkinter desktop UI (observed in `jarvis_desktop.py`), Flutter/Dart Android UI (observed in `ui/lib/main.dart`), Three.js/WebGL local assets (proposed), Flutter asset packaging, Windows packaging scripts and GitHub Actions.

## Global Constraints

- Preserve Hugging Face Inference API provider configuration and existing chat, voice, IPC, and native Android bridge behavior.
- All visualization scripts and assets must be packaged locally; no CDN dependency at runtime.
- Runtime visual states must reflect actual microphone, request, TTS, and error events.
- Show system telemetry only when real data is available; mark unavailable values clearly.
- Keep visual effects adaptive for Windows 10 x64, Ryzen 5 2600, 16 GB RAM, Radeon RX 570, and Android devices.
- Do not delete legacy visual assets until the replacement is integrated and verified on both platforms.
- Do not delete branches or unrelated repositories as part of this plan.
- Work on `feature/unified-3d-interface`, based on `foundation`; retain a rollback path.

---

### Task 1: Define and test the shared visualization contract

**Files:**
- Create: `ui/assets/jarvis_scene/index.html` (proposed)
- Create: `ui/assets/jarvis_scene/scene.js` (proposed)
- Create: `ui/assets/jarvis_scene/scene.css` (proposed)
- Create: `ui/test/jarvis_scene_contract_test.dart` (proposed)
- Modify: `ui/pubspec.yaml`

**Interfaces:**
- Scene input message: `{type: "state", state: "idle" | "listening" | "processing" | "speaking" | "error", audioLevel?: number, loadLevel?: number, message?: string}`.
- Scene telemetry is optional and separately typed; absent values render as unavailable, never as zero or fabricated values.
- Scene exposes a single JavaScript entry point `window.jarvisScene.setState(payload)` and reports readiness to its host.

- [ ] **Step 1: Add contract tests**
  Test accepted states, optional telemetry behavior, and explicit error display; verify unknown states do not crash the scene.
- [ ] **Step 2: Verify the focused test fails**
  Run: `cd ui && flutter test test/jarvis_scene_contract_test.dart`
  Expected: tests fail until the scene contract/adapter is implemented.
- [ ] **Step 3: Implement the local scene**
  Create a responsive dark HUD with the animated central 3D core, rotating rings, particles, glow, Russian labels, and reduced-effects mode. Bundle the exact Three.js build locally; do not use CDN imports.
- [ ] **Step 4: Verify the focused test passes**
  Run: `cd ui && flutter test test/jarvis_scene_contract_test.dart`
  Expected: all contract tests pass.
- [ ] **Step 5: Check packaging and local asset references**
  Run: `cd ui && flutter pub get && flutter analyze`
  Expected: dependencies resolve and no new analyzer errors are introduced.
- [ ] **Step 6: Commit the passing deliverable**
  Commit message: `feat: add local JARVIS 3D scene and state contract`.

### Task 2: Integrate the scene with the Android Flutter interface

**Files:**
- Modify: `ui/lib/main.dart`
- Modify: `ui/pubspec.yaml`
- Create: `ui/lib/jarvis_scene_view.dart` (proposed)
- Test: `ui/test/jarvis_scene_view_test.dart` (proposed)

**Interfaces:**
- Flutter view receives the current real assistant state from `BusyaHomePage` and sends it to the scene adapter.
- Preserve existing `jarvis.voice` MethodChannel, `jarvis.voice.events` EventChannel, and `JarvisIpc` interactions.

- [ ] **Step 1: Add widget tests**
  Assert that state changes from idle to listening, processing, speaking and error are passed to the scene adapter; ensure missing telemetry is shown as unavailable.
- [ ] **Step 2: Verify the focused tests fail**
  Run: `cd ui && flutter test test/jarvis_scene_view_test.dart`
  Expected: tests fail before integration.
- [ ] **Step 3: Implement the Android scene host**
  Use a WebView capable of loading only the bundled local scene. Add the minimum required package and Android configuration; do not weaken network/security permissions for remote scripts.
- [ ] **Step 4: Verify focused tests pass**
  Run: `cd ui && flutter test test/jarvis_scene_view_test.dart`
  Expected: state mapping and loading/error fallback tests pass.
- [ ] **Step 5: Run Flutter checks and Android build**
  Run: `cd ui && flutter analyze && flutter test && flutter build apk --debug`
  Expected: analyzer and tests pass and the debug APK builds; record if the environment lacks Android tooling.
- [ ] **Step 6: Commit the passing deliverable**
  Commit message: `feat(android): integrate shared JARVIS 3D scene`.

### Task 3: Integrate the scene with the Windows desktop UI

**Files:**
- Modify: `jarvis_desktop.py`
- Modify: Windows packaging workflow/build configuration after inspecting its asset-inclusion rules
- Create: a small Windows scene-host adapter at a path chosen to match the existing packaging conventions (proposed)
- Test: add focused tests under the existing Python test layout after confirming its naming conventions

**Interfaces:**
- Desktop UI forwards the existing runtime status and available telemetry to `window.jarvisScene.setState(payload)`.
- Preserve Tkinter command handling, current Python agent integration, microphone/wake-word behavior, TTS, and Hugging Face settings.

- [ ] **Step 1: Add focused adapter tests**
  Cover state mapping, unavailable telemetry, scene-load failure, and fallback to a readable error/status display.
- [ ] **Step 2: Verify the focused tests fail**
  Run the exact test command selected from the repository's existing test conventions.
  Expected: tests fail before the adapter exists.
- [ ] **Step 3: Implement the Windows host**
  Select an embeddable WebView approach compatible with the existing desktop shell and packaging constraints. Do not silently replace Tkinter or require a CDN; if a WebView runtime is not bundled or available, show a clear fallback rather than a blank window.
- [ ] **Step 4: Verify focused tests pass**
  Run the focused Python test command.
  Expected: adapter tests pass.
- [ ] **Step 5: Run Windows tests and packaging checks**
  Run: `python -m unittest discover -s tests` and the repository's documented Windows build script on a Windows runner.
  Expected: existing tests pass and the package includes the local scene assets.
- [ ] **Step 6: Commit the passing deliverable**
  Commit message: `feat(windows): integrate shared JARVIS 3D scene`.

### Task 4: Remove superseded visuals and verify both platforms

**Files:**
- Modify or delete only confirmed obsolete visual files, initially candidates: `ui/jarvis_reactor.html` and legacy-only portions of `ui/lib/jarvis_reactor.dart`.
- Modify: documentation and workflows only where they refer to the retired visual component.
- Tests: existing Flutter/Python tests and platform build workflows.

**Interfaces:**
- Existing platform shells continue to expose the same assistant controls and runtime state.
- New scene is the only active primary visual surface on both platforms.

- [ ] **Step 1: Add regression checks**
  Assert the app entry points mount the new scene and that no active imports/references depend on removed legacy visual components.
- [ ] **Step 2: Verify regression checks fail before cleanup**
  Run the focused Flutter/Python tests and reference search.
  Expected: tests or search identify remaining active references to the old visual component.
- [ ] **Step 3: Remove only superseded assets**
  Delete old files only after all active references are migrated. Do not remove files with non-visual responsibilities or files whose usage is unclear.
- [ ] **Step 4: Verify cleanup**
  Run Flutter analyzer/tests, Python tests, and searches for old component references.
  Expected: no active entry point references the retired visual, and test suites pass.
- [ ] **Step 5: Run platform builds**
  Run `cd ui && flutter build apk --release` and the documented Windows packaging script on suitable runners.
  Expected: both packages contain the local scene and start without a network connection for visualization.
- [ ] **Step 6: Commit the passing deliverable**
  Commit message: `refactor: retire legacy JARVIS visualizations`.

## Explicitly unresolved implementation seam

The exact Windows WebView host must be chosen after inspecting the desktop shell's widget lifecycle and the current packaging scripts. The implementation must preserve the existing shell where possible, bundle or clearly document the required runtime, and provide a visible fallback if the WebView cannot start. No branch deletions are included until a separate audit proves that every unique commit is either merged or safely preserved.