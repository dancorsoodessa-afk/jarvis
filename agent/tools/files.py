"""Enhanced error handling for file operations."""

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger("jarvis.tools.files")


def search(pattern: str, root: str = ".") -> List[str]:
    """
    Recursively search for files matching pattern.
    
    Args:
        pattern: Glob pattern (e.g., "*.txt", "test_*.py")
        root: Root directory to search
    
    Returns:
        List of matching file paths
    
    Raises:
        ValueError: If root path doesn't exist or is invalid
    """
    try:
        root_path = Path(root).resolve()
        
        if not root_path.exists():
            logger.error(f"Search root does not exist: {root}")
            raise ValueError(f"Root path does not exist: {root}")
        
        if not root_path.is_dir():
            logger.error(f"Search root is not a directory: {root}")
            raise ValueError(f"Root path is not a directory: {root}")
        
        logger.info(f"Searching for {pattern} in {root_path}")
        
        results = [str(p) for p in root_path.glob(f"**/{pattern}")]
        logger.info(f"Found {len(results)} matches for {pattern}")
        
        return results
    
    except (PermissionError, OSError) as e:
        logger.error(f"File system error during search: {e}")
        raise ValueError(f"Cannot access path: {e}")


def delete(path: str) -> str:
    """
    Delete a file (not directories).
    
    Args:
        path: Path to file to delete
    
    Returns:
        Confirmation message
    
    Raises:
        ValueError: If path is invalid or is a directory
        RuntimeError: If deletion fails
    """
    try:
        target = Path(path).resolve()
        
        if not target.exists():
            logger.error(f"Delete target does not exist: {path}")
            raise ValueError(f"File does not exist: {path}")
        
        if target.is_dir():
            logger.error(f"Attempted to delete directory: {path}")
            raise ValueError(f"Cannot delete directories: {path}")
        
        logger.warning(f"Deleting file: {target}")
        target.unlink()
        
        logger.info(f"Deleted: {target}")
        return f"Deleted: {target}"
    
    except PermissionError as e:
        logger.error(f"Permission denied deleting {path}: {e}")
        raise RuntimeError(f"Permission denied: {e}")
    except Exception as e:
        logger.error(f"Error deleting {path}: {e}", exc_info=True)
        raise RuntimeError(f"Deletion failed: {e}")
