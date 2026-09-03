"""Entry points:
  python -m agent            interactive CLI
  python -m agent --ipc      JSON-lines over stdin/stdout (for Flutter UI)
  python -m agent --ipc-tcp [port]  JSON-lines over TCP (remote UI)
"""

import sys
import logging

from .logger import setup_logging, get_logger
from .runtime import build_agent
from . import ipc

# Initialize logging
setup_logging()
logger = get_logger("main")


def main():
    try:
        logger.info("Starting JARVIS")
        agent = build_agent()
        args = sys.argv[1:]

        if "--ipc" in args:
            logger.info("Starting IPC server (stdio)")
            ipc.serve_stdio(agent)
            return

        if "--ipc-tcp" in args:
            i = args.index("--ipc-tcp")
            port = int(args[i + 1]) if i + 1 < len(args) else 8765
            logger.info(f"Starting IPC server (TCP port {port})")
            ipc.serve_tcp(agent, port=port)
            return

        # Interactive CLI mode
        names = ", ".join(f"/{n}" for n in agent.tools.names())
        print(f"JARVIS готов (provider: {agent.provider.name}). "
              f"Инструменты: {names}. Выход: /exit, Ctrl+C.")
        logger.info(f"Interactive mode started with {len(agent.tools.names())} tools")
        
        while True:
            try:
                message = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                logger.info("JARVIS shutting down (user interrupt)")
                break
            if message.strip() in ("/exit", "/quit"):
                logger.info("JARVIS shutting down (user command)")
                break
            result = agent.handle(message)
            print(result.text)
    
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
