"""Logging setup for Jarvis.

Rotating file log (JARVIS_LOG, default jarvis.log next to the memory file)
+ optional stderr console output (JARVIS_LOG_CONSOLE=1, used by CLI).
Everything is stdlib; the log never blocks the agent (best-effort).
Sensitive data is filtered from logs to prevent accidental disclosure.
"""
import logging
import logging.handlers
import os
import re
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
MAX_BYTES = 1_000_000  # ~1 MB per file
BACKUPS = 3


def _log_path() -> Path:
    default = Path(os.environ.get("JARVIS_MEMORY", "jarvis_memory.json"))
    return Path(os.environ.get("JARVIS_LOG", str(default.with_name("jarvis.log"))))


def _filter_sensitive_data(record):
    """Filter sensitive data from log records to prevent accidental disclosure."""
    if hasattr(record, 'msg') and isinstance(record.msg, str):
        # Filter out potential API keys, tokens, passwords
        msg = record.msg
        
        # Replace potential API keys (common patterns)
        msg = re.sub(r'(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)[=:]\s*[\w\-]+', 
                     r'\1=[FILTERED]', msg)
        
        # Replace potential file paths that might contain sensitive info
        msg = re.sub(r'(?i)(/etc/passwd|/etc/shadow|/root/|\\\\Users\\\\.*\\\\Documents|\\\\Users\\\\.*\\\\Desktop)', 
                     '[FILTERED_PATH]', msg)
        
        # Replace potential SQL queries that might contain sensitive data
        msg = re.sub(r'(?i)(SELECT.*FROM.*WHERE|INSERT.*INTO|UPDATE.*SET|DELETE.*FROM)', 
                     '[FILTERED_QUERY]', msg)
        
        record.msg = msg
    
    return True


def setup(level: int | None = None) -> logging.Logger:
    """Configure 'jarvis' logger with a rotating file handler. Idempotent."""
    logger = logging.getLogger("jarvis")
    if getattr(logger, "_jarvis_configured", False):
        return logger
    logger.setLevel(level or getattr(logging, os.environ.get("JARVIS_LOG_LEVEL", "INFO").upper(), logging.INFO))
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        fh.addFilter(_filter_sensitive_data)
        logger.addHandler(fh)
    except OSError:
        pass  # logging must never break the agent
    if os.environ.get("JARVIS_LOG_CONSOLE") == "1":
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(LOG_FORMAT))
        sh.addFilter(_filter_sensitive_data)
        logger.addHandler(sh)
    logger._jarvis_configured = True
    return logger


def get(name: str = "jarvis") -> logging.Logger:
    return setup().getChild(name)