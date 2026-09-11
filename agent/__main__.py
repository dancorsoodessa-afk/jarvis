"""Entry points:
  python -m agent            interactive CLI
  python -m agent --ipc      JSON-lines over stdin/stdout (for Flutter UI)
  python -m agent --ipc-tcp [port]  JSON-lines over TCP (remote UI)
"""

import sys

from .runtime import build_agent
from . import ipc


def main():
    agent = build_agent()
    args = sys.argv[1:]

    if "--ipc" in args:
        ipc.serve_stdio(agent)
        return

    if "--ipc-tcp" in args:
        i = args.index("--ipc-tcp")
        port = int(args[i + 1]) if i + 1 < len(args) else 8765
        ipc.serve_tcp(agent, port=port)
        return

    if "--voice" in args:
        from .voice_loop import VoiceLoop
        VoiceLoop(agent).run()
        return

    if "--memory-clear" in args:
        from .memory import SessionMemory
        from .memory.store import MemoryStore
        from .config import Settings
        store = MemoryStore(Settings.from_env().memory_path)
        print(SessionMemory(store).clear())
        return

    names = ", ".join(f"/{n}" for n in agent.tools.names())
    print(f"JARVIS готов (provider: {agent.provider.name}). "
          f"Инструменты: {names}. Выход: /exit, Ctrl+C.")
    while True:
        try:
            message = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if message.strip() in ("/exit", "/quit"):
            break
        result = agent.handle(message)
        print(result.text)


if __name__ == "__main__":
    main()
