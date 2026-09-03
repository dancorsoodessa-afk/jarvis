"""Logging configuration for JARVIS agent."""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


def setup_logging(
    log_dir: str = "logs",
    log_level: int = logging.INFO,
    console: bool = True
) -> logging.Logger:
    """
    Configure logging with both file and console handlers.
    
    Args:
        log_dir: Directory for log files
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console: Whether to also log to console
    
    Returns:
        Configured logger instance
    """
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    logger = logging.getLogger("jarvis")
    logger.setLevel(log_level)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Format: timestamp | level | name | message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Main log file (all levels)
    main_handler = logging.handlers.RotatingFileHandler(
        log_path / "jarvis.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    main_handler.setLevel(log_level)
    main_handler.setFormatter(formatter)
    logger.addHandler(main_handler)
    
    # Error log file (errors and critical)
    error_handler = logging.handlers.RotatingFileHandler(
        log_path / "jarvis_errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get or create a logger with the given name."""
    if name is None:
        return logging.getLogger("jarvis")
    return logging.getLogger(f"jarvis.{name}")
