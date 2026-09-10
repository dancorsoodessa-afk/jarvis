# JARVIS AI workflow

## Repository change policy

- Project changes are made by the AI agent through repository tooling.
- The human operator does not manually edit project files.
- When a code or configuration change is needed, the AI agent applies it to the active development branch and reports the resulting commit.
- The human operator only runs commands provided by the AI agent and returns the command output.
- Do not instruct the human operator to manually create, edit, or patch files unless the operator explicitly asks for manual editing.

## Verification policy

- Keep the `foundation` branch green.
- Run the full test suite after meaningful code/configuration changes.
- Before release, verify Windows packaging and run a Windows executable smoke test.
