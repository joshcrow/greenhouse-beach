import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

def log(msg: str) -> None:
    """Simple logger with timestamp."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{timestamp}] [stats] {msg}", flush=True)


def _load_stats_file(path: str) -> Optional[Dict[str, Any]]:
    """Load a JSON stats file if it exists, else return None.

    Expected structure (MVP):
    {
      "window_start": "ISO8601",
      "window_end": "ISO8601",
      "metrics": {
        "indoor_temp_min": ...,
        "indoor_temp_max": ...,
        ...
      }
    }
    """

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError) as exc:  # noqa: PERF203
        log(f"Failed to load 24h stats from {path}: {exc}")
        return None


def get_24h_stats(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Return 24-hour min/max stats for sensors.

    MVP: read from a JSON file at STATS_24H_PATH (default /app/data/stats_24h.json).
    If the file is missing or invalid, log a warning and return an empty dict.
    """

    if now is None:
        now = datetime.utcnow()

    stats_path = os.getenv("STATS_24H_PATH", "/app/data/stats_24h.json")
    data = _load_stats_file(stats_path)
    if not data:
        log(
            "WARNING: 24h stats file not found or invalid; "
            "Sensors card will fall back to current values / N/A."
        )
        return {}

    # Optional: basic window sanity check (non-fatal)
    window_start_str = data.get("window_start")
    window_end_str = data.get("window_end")
    try:
        if window_start_str and window_end_str:
            window_start = datetime.fromisoformat(window_start_str)
            window_end = datetime.fromisoformat(window_end_str)
            # Rough 24h check (non-strict, just log)
            if window_end < window_start or window_end > now + timedelta(minutes=5):
                log(
                    "WARNING: 24h stats window appears inconsistent: "
                    f"start={window_start_str}, end={window_end_str}"
                )
    except Exception:  # noqa: BLE001
        # If parsing fails, we still return metrics; just log once.
        log("WARNING: Failed to parse 24h stats window timestamps.")

    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        log("WARNING: 24h stats file missing 'metrics' dict; ignoring.")
        return {}

    return metrics
