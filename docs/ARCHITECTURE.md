# Architecture

Flutter UI
  -> IPC
Python Agent Core
  -> AIProvider
     -> Cloud
     -> Local Vulkan / llama.cpp
  -> ToolRegistry
  -> MemoryStore

The UI never knows which AI model is active.
The agent never depends directly on Ollama.
Tools are isolated and can require confirmation.

## IPC protocol (agent/ipc.py)

JSON-lines, one object per line, UTF-8.

Requests:
- `{"id": N, "type": "message", "text": "..."}`
- `{"id": N, "type": "tool", "tool": "search", "args": ["*.txt", "C:\\"]}`
- `{"id": N, "type": "tools"}` — list registered tools
- `{"id": N, "type": "ping"}`

Responses: `{"id": N, "type": "message", "text", "provider", "tool_used",
"needs_confirmation"}` or `{"id": N, "type": "error", "message"}`.

Transports: `jarvis.exe --ipc` (stdin/stdout, Flutter spawns the child
process) or `jarvis.exe --ipc-tcp [port]` (remote UI, default 127.0.0.1:8765).
Dart client: ui/jarvis_client.dart.
