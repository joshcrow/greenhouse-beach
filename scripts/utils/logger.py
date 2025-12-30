"""Shared logging utility for Greenhouse Gazette scripts.

Provides consistent timestamped logging across all modules.

Usage:
    from utils.logger import create_logger
    log = create_logger("my_module")
    log("Something happened")
    # Output: [2024-12-30T12:00:00Z] [my_module] Something happened
"""

from datetime import datetime
from typing import Callable


def create_logger(module_name: str) -> Callable[[str], None]:
    """Create a logger function for a specific module.
    
    Args:
        module_name: Name to include in log prefix (e.g., "publisher", "narrator")
    
    Returns:
        A log function that prints timestamped messages with the module prefix.
    """
    def log(message: str) -> None:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[{ts}] [{module_name}] {message}", flush=True)
    return log
