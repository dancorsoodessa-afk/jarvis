## JARVIS — Personal AI Agent for Windows x64

Personal AI desktop assistant with cloud-first architecture, local GPU inference support (Vulkan), and cross-platform Flutter UI.

### ✨ Features

- **Cloud-first AI** — Primary: cloud provider (configurable URL), fallback: local llama.cpp + Vulkan
- **13+ Built-in Tools** — File management, process control, screenshots, audio, network, web, etc.
- **IPC Protocol** — JSON-line communication for Flutter UI integration
- **Memory System** — Conversation history persistence
- **Reminders & Scheduling** — Built-in reminder service
- **Comprehensive Logging** — Rotating logs with separate error tracking
- **Cross-platform** — Windows x64 primary, Linux/Mac support in progress

### 🎯 Quick Start

#### Installation

```bash
pip install -e .
```

#### Run Interactive CLI

```bash
python -m agent
```

Output:
```
JARVIS готов (provider: cloud). Инструменты: /status, /search, /delete, /launch, /volume, ...
> привет
echo: привет
```

#### Run with Flutter UI (IPC mode)

```bash
python -m agent --ipc
```

#### Run with Remote TCP Server

```bash
python -m agent --ipc-tcp 8765
```

#### Build Standalone Executable

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Result: `dist/jarvis.exe` (single file, no Python needed)

### 🔧 Configuration

Environment variables (see `agent/config.py`):

```bash
# Provider selection
JARVIS_LOCAL=1                              # Use local inference (default: 0)

# Cloud provider
JARVIS_CLOUD_URL=https://api.example.com   # Cloud API endpoint

# Local inference
JARVIS_LLAMA_CLI=/path/to/llama-cli        # llama.cpp binary
JARVIS_MODEL=/path/to/model.gguf           # Model weights
JARVIS_CTX=2048                            # Context size
JARVIS_THREADS=6                           # Worker threads

# Storage
JARVIS_MEMORY=jarvis_memory.json           # Memory file path
```

### 📚 Available Tools

#### System & Process
- `/status` — System information
- `/ps [filter]` — List processes
- `/kill <pid>` — Kill process (requires confirmation)

#### File Management
- `/search <pattern> [root]` — Find files recursively
- `/delete <path>` — Delete file (requires confirmation)

#### Applications
- `/launch <command>` — Launch application (requires confirmation)

#### Audio
- `/volume` — Get current volume
- `/set_volume <0-100>` — Set volume level

#### Media
- `/screenshot` — Capture screen to file

#### Clipboard
- `/clip_get` — Get clipboard content
- `/clip_set <text>` — Set clipboard content

#### 🆕 Network (v0.2.0)
- `/internet` — Check internet connectivity
- `/ping <host>` — Ping a host
- `/dns` — Show DNS configuration

#### 🆕 Web (v0.2.0)
- `/open <url>` — Open URL in default browser
- `/title <url>` — Fetch webpage title
- `/websearch <query>` — Search DuckDuckGo

#### Reminders
- `/remind <text>` — Add reminder
- `/reminders` — List pending reminders

### 🏗️ Architecture

```
jarvis/
├── agent/
│   ├── core.py              # Main agent logic
│   ├── runtime.py           # Initialization & tool registration
│   ├── config.py            # Settings from environment
│   ├── logger.py            # Logging system (NEW)
│   ├── ipc.py               # JSON-line IPC protocol
│   ├── memory/
│   │   └── store.py         # Conversation history
│   ├── providers/
│   │   ├── cloud.py         # Cloud AI provider (with retry)
│   │   └── local_vulkan.py  # Local llama.cpp + Vulkan
│   ├── tools/
│   │   ├── system.py        # System info
│   │   ├── files.py         # File operations
│   │   ├── apps.py          # App launching
│   │   ├── audio.py         # Audio control
│   │   ├── screenshot.py    # Screen capture
│   │   ├── processes.py     # Process management
│   │   ├── clipboard.py     # Clipboard access
│   │   ├── network.py       # Network utilities (NEW)
│   │   ├── web.py           # Web utilities (NEW)
│   │   └── registry.py      # Tool registration & execution
│   └── reminders.py         # Reminder service
├── ui/
│   ├── main.dart            # Flutter app entry
│   ├── jarvis_client.dart   # IPC client
│   └── pubspec.yaml
├── scripts/
│   ├── build_exe.ps1        # Build Windows executable
│   └── check_vulkan.ps1     # Check Vulkan support
├── tests/
│   ├── test_agent.py        # Agent logic tests
│   ├── test_tools.py        # Tool integration tests
│   ├── test_network.py      # Network tool tests (NEW)
│   ├── test_web.py          # Web tool tests (NEW)
│   ├── test_cloud_provider.py # Cloud provider retry tests (NEW)
│   └── test_ipc_protocol.py # IPC protocol tests (NEW)
└── docs/
    ├── ARCHITECTURE.md
    └── LOCAL_AI.md
```

### 🧪 Testing

Run all tests:

```bash
python -m unittest discover -s tests
```

Run specific test:

```bash
python -m unittest tests.test_agent.TestAgent.test_generate_and_memory
```

### 📊 Logging

Logs are written to:

- `logs/jarvis.log` — All events (rotating, 10 MB max, 5 backups)
- `logs/jarvis_errors.log` — Errors only (rotating, 5 MB max, 3 backups)
- Console — Real-time output

Log format: `timestamp | level | logger_name | message`

Example:
```
2026-09-03 10:15:17 | INFO     | jarvis.runtime | Building agent with settings: use_local=False
2026-09-03 10:15:18 | INFO     | jarvis.runtime | Registered 16 tools
2026-09-03 10:15:18 | INFO     | jarvis.main | Starting JARVIS
```

### 🔄 Provider Selection

**Cloud Provider (Default)**
- Fast, no local GPU needed
- Requires `JARVIS_CLOUD_URL` environment variable
- Automatic retry with exponential backoff (3 attempts)
- Graceful error messages

**Local Provider (Opt-in)**
- Set `JARVIS_LOCAL=1`
- Requires llama.cpp + Vulkan
- GPU-accelerated inference
- See `docs/LOCAL_AI.md` for setup

### 🤝 IPC Protocol

Communication format: JSON-lines (one JSON object per line)

**Request** (from UI → Agent):
```json
{"message": "привет"}
```

**Response** (from Agent → UI):
```json
{"text": "Привет! Как дела?", "provider": "cloud", "tool_used": null, "needs_confirmation": false}
```

**Tool Confirmation Flow**:
```
UI: {"message": "/delete file.txt"}
Agent: {"text": "Инструмент «delete» требует подтверждения. Выполнить? (yes/да)", "needs_confirmation": true}
UI: {"message": "да"}
Agent: {"text": "Deleted: /path/to/file.txt", "tool_used": "delete"}
```

### 📱 Flutter UI

Start the Flutter app:

```bash
cd ui
flutter pub get
flutter run -d windows    # or: flutter build windows
```

The UI automatically:
1. Spawns `jarvis.exe` (or Python fallback)
2. Communicates via IPC protocol
3. Displays the Jarvis reactor animation
4. Sends/receives messages

For a preview of the reactor without Flutter:
```bash
open ui/jarvis_reactor.html
```

### 🚀 Performance Targets

Tested on: AMD Ryzen 5 2600 + 16 GB RAM + RX 570 4 GB

- Cloud response: ~1-5 seconds (depends on provider)
- Local inference: ~10-30 seconds (depends on model size)
- Tool execution: <500 ms
- Memory footprint: ~100-200 MB (CLI), ~300 MB (with UI)

### 🛠️ Development

**Run tests before committing**:
```bash
python -m unittest discover -s tests -v
```

**Code structure**:
- `agent/core.py` — Core agent dispatch logic
- `agent/runtime.py` — Initialization & configuration
- `agent/tools/` — Tool implementations
- `tests/` — Comprehensive test coverage

**Adding new tools**:

1. Create function in `agent/tools/mytool.py`:
```python
def my_action(param: str) -> str:
    """Action description."""
    logger.info(f"Executing: {param}")
    return f"Result: {param}"
```

2. Register in `agent/runtime.py`:
```python
tools.register("myaction", my_action, confirm=False)
```

3. Add tests in `tests/test_mytool.py`

### 📝 License

MIT

### 🔗 Links

- Repository: https://github.com/dancorsoodessa-afk/jarvis
- Issues: https://github.com/dancorsoodessa-afk/jarvis/issues
- Architecture: `docs/ARCHITECTURE.md`
- Local AI Setup: `docs/LOCAL_AI.md`

---

**Version**: 0.2.0 (dev/improvements)  
**Last Updated**: 2026-09-03  
**Python**: 3.10+
