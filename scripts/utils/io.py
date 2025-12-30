"""Shared I/O utilities for Greenhouse Gazette scripts.

Provides atomic file operations to protect against corruption,
especially important for SD card reliability on Raspberry Pi.

Usage:
    from utils.io import atomic_write_json, atomic_read_json
    
    # Write JSON atomically (temp file + fsync + rename)
    atomic_write_json("/path/to/file.json", {"key": "value"})
    
    # Read JSON with fallback
    data = atomic_read_json("/path/to/file.json", default={})
"""

import json
import os
from typing import Any, Optional


def atomic_write_json(
    path: str,
    data: Any,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """Write JSON data atomically to protect against corruption.
    
    Uses the temp-file + fsync + rename pattern to ensure data
    is fully written to disk before the original file is replaced.
    
    Args:
        path: Target file path
        data: Data to serialize as JSON
        indent: JSON indentation level (default 2)
        ensure_ascii: If False, allow non-ASCII characters (default False)
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def atomic_read_json(
    path: str,
    default: Optional[Any] = None,
) -> Any:
    """Read JSON file with graceful fallback on error.
    
    Args:
        path: File path to read
        default: Value to return if file doesn't exist or is invalid
    
    Returns:
        Parsed JSON data, or default if read fails
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default
