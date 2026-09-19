# JARVIS AI workflow

## Repository change policy

- Project changes are made by the AI agent through repository tooling.
- The human operator does not manually edit project files.
- When a code or configuration change is needed, the AI agent applies it to the active development branch and reports the resulting commit.
- The human operator only runs commands provided by the AI agent and returns the command output.
- Do not instruct the human operator to manually create, edit, or patch files unless the operator explicitly asks for manual editing.

## Grimoire coding workflow

- This repository uses Grimoire for versioned AI-agent skills and coding guidance.
- grimoire.toml is the source of truth for the selected Grimoire bundle.
- Use the Grimoire skill set for repository analysis, implementation planning, review, and verification when the coding-agent runtime provides it.
- Do not treat generated client files as source; Grimoire regenerates them from the declaration/lock state.
- Keep Grimoire configuration reproducible and do not commit generated .grimoire/, .agents/, .claude/, or other client-rendered output unless explicitly required.

## Verification policy

- Keep the foundation branch green.
- Run the full test suite after meaningful code/configuration changes.
- For Android changes, verify source -> GitHub Actions -> APK artifact -> APK signature/manifest/hash before calling a build ready.
- Before release, verify Windows packaging and run a Windows executable smoke test.
