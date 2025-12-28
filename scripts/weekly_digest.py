#!/usr/bin/env python3
"""Weekly Digest Generator for the Greenhouse Gazette.

Generates a weekly summary email with trends, notable events,
and a narrative overview of the past week.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [weekly] {message}", flush=True)


STATS_PATH = os.getenv("STATS_PATH", "/app/data/stats_24h.json")
STATUS_PATH = os.getenv("STATUS_PATH", "/app/data/status.json")
WEEKLY_STATS_PATH = os.getenv("WEEKLY_STATS_PATH", "/app/data/stats_weekly.json")


def load_weekly_stats() -> Dict[str, Any]:
    """Load or initialize weekly stats file."""
    if os.path.exists(WEEKLY_STATS_PATH):
        try:
            with open(WEEKLY_STATS_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            log(f"Error loading weekly stats: {e}")
    return {"days": [], "week_start": None}


def save_weekly_stats(stats: Dict[str, Any]) -> None:
    """Save weekly stats to file."""
    try:
        with open(WEEKLY_STATS_PATH, "w") as f:
            json.dump(stats, f, indent=2, default=str)
    except Exception as e:
        log(f"Error saving weekly stats: {e}")


def record_daily_snapshot() -> None:
    """Record today's stats to the weekly accumulator.

    Call this daily (e.g., at end of day or during daily email).
    """
    weekly = load_weekly_stats()

    # Load current 24h stats
    if not os.path.exists(STATS_PATH):
        log("No 24h stats found, skipping daily snapshot")
        return

    try:
        with open(STATS_PATH, "r") as f:
            daily_stats = json.load(f)
    except Exception as e:
        log(f"Error loading 24h stats: {e}")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    # Add today's snapshot
    snapshot = {
        "date": today,
        "stats": daily_stats,
        "recorded_at": datetime.utcnow().isoformat(),
    }

    # Keep only last 7 days
    weekly["days"] = [d for d in weekly.get("days", []) if d["date"] != today]
    weekly["days"].append(snapshot)
    weekly["days"] = weekly["days"][-7:]  # Keep last 7 days

    if not weekly.get("week_start"):
        weekly["week_start"] = today

    save_weekly_stats(weekly)
    log(f"Recorded daily snapshot for {today}")


def compute_weekly_summary(weekly: Dict[str, Any]) -> Dict[str, Any]:
    """Compute weekly aggregates from daily snapshots."""
    days = weekly.get("days", [])
    if not days:
        return {}

    summary = {
        "days_recorded": len(days),
        "week_start": days[0]["date"] if days else None,
        "week_end": days[-1]["date"] if days else None,
    }

    # Aggregate temperature stats
    all_temps = []
    all_humidities = []

    for day in days:
        stats = day.get("stats", {})
        # Handle nested metrics structure
        metrics = stats.get("metrics", {})
        # Collect all temperature values from both direct stats and metrics
        for key, val in {**stats, **metrics}.items():
            if "temp" in key.lower() and isinstance(val, (int, float)):
                all_temps.append(val)
            if "humidity" in key.lower() and isinstance(val, (int, float)):
                all_humidities.append(val)

    if all_temps:
        summary["temp_min"] = round(min(all_temps))
        summary["temp_max"] = round(max(all_temps))
        summary["temp_avg"] = round(sum(all_temps) / len(all_temps))

    if all_humidities:
        summary["humidity_min"] = round(min(all_humidities))
        summary["humidity_max"] = round(max(all_humidities))
        summary["humidity_avg"] = round(sum(all_humidities) / len(all_humidities))

    return summary
