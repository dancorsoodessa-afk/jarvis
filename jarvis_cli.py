"""Entry point for the packaged exe (relative imports fail in __main__.py)."""

from agent.__main__ import main

if __name__ == "__main__":
    main()
