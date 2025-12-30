"""Coast & Sky Service for The Greenhouse Gazette.

Provides tide predictions (NOAA CO-OPS) and astronomical event summaries
(meteor showers, named moon events) from static calendars.

Station: 8652226 (Jennette's Pier, NC)
Datum: MLLW
Units: Feet
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from utils.logger import create_logger
from utils.io import atomic_write_json


# NOAA CO-OPS configuration
NOAA_STATION_ID = os.getenv("NOAA_TIDE_STATION", "8652226")
NOAA_STATION_NAME = "Jennette's Pier, NC"
NOAA_BASE_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

# Cache configuration - persist to mounted volume (survives container restarts)
CACHE_PATH = os.getenv("COAST_SKY_CACHE_PATH", "/app/data/coast_sky_cache.json")
CACHE_TTL_HOURS = int(os.getenv("COAST_SKY_CACHE_TTL_HOURS", "6"))

# Calendar paths
CALENDARS_DIR = os.getenv("CALENDARS_DIR", "/app/data/calendars")

# Timezone for local time formatting
TZ_NAME = os.getenv("TZ", "America/New_York")


log = create_logger("coast_sky")


def _get_local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(TZ_NAME)
    except Exception:
        return ZoneInfo("America/New_York")


def _load_cache() -> Optional[Dict[str, Any]]:
    """Load cached coast/sky data if fresh enough."""
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache.get("cached_at", ""))
        if datetime.utcnow() - cached_at < timedelta(hours=CACHE_TTL_HOURS):
            log(f"Using cached coast/sky data from {cached_at.isoformat()}")
            return cache.get("data")
    except Exception as exc:
        log(f"Cache read error: {exc}")
    return None


def _save_cache(data: Dict[str, Any]) -> None:
    """Save coast/sky data to cache."""
    try:
        cache = {
            "cached_at": datetime.utcnow().isoformat(),
            "data": data,
        }
        atomic_write_json(CACHE_PATH, cache, indent=None)
    except Exception as exc:
        log(f"Cache write error: {exc}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.RequestException, requests.Timeout)),
    reraise=False,
)
def _fetch_noaa_data(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Internal function to fetch NOAA data with retry logic."""
    resp = requests.get(NOAA_BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _fetch_noaa_tides(date_local: datetime) -> Dict[str, Any]:
    """Fetch tide predictions from NOAA CO-OPS for the given date.

    Returns structured tide_summary or empty dict on failure.
    """
    # Request predictions for today and tomorrow (48 hours)
    begin_date = date_local.strftime("%Y%m%d")
    end_date = (date_local + timedelta(days=1)).strftime("%Y%m%d")

    params = {
        "begin_date": begin_date,
        "end_date": end_date,
        "station": NOAA_STATION_ID,
        "product": "predictions",
        "datum": "MLLW",
        "units": "english",  # feet
        "time_zone": "lst_ldt",  # local standard/daylight time
        "interval": "hilo",  # high/low only
        "format": "json",
    }

    try:
        log(
            f"Fetching NOAA tides for station {NOAA_STATION_ID} ({begin_date} to {end_date})"
        )
        data = _fetch_noaa_data(params)
        if data is None:
            log("NOAA API request failed after retries")
            return None

        predictions = data.get("predictions", [])
        if not predictions:
            log("NOAA returned no predictions")
            return {}

        high_tides = []
        low_tides = []

        for pred in predictions:
            time_str = pred.get("t", "")
            height_str = pred.get("v", "0")
            tide_type = pred.get("type", "")  # "H" for high, "L" for low

            try:
                height_ft = round(float(height_str), 1)
            except (ValueError, TypeError):
                height_ft = 0.0

            entry = {
                "time_local": time_str,
                "height_ft": height_ft,
            }

            if tide_type == "H":
                high_tides.append(entry)
            elif tide_type == "L":
                low_tides.append(entry)

        # Compute today's extremes
        today_str = date_local.strftime("%Y-%m-%d")
        today_highs = [h for h in high_tides if h["time_local"].startswith(today_str)]
        today_lows = [
            low for low in low_tides if low["time_local"].startswith(today_str)
        ]

        max_high_ft = max((h["height_ft"] for h in today_highs), default=None)
        min_low_ft = min((low["height_ft"] for low in today_lows), default=None)

        # Simple king tide heuristic: if max high > 5.5 ft at Jennette's Pier
        # (this threshold should be tuned for local conditions)
        KING_TIDE_THRESHOLD_FT = 5.5
        is_king_tide_window = (
            max_high_ft is not None and max_high_ft >= KING_TIDE_THRESHOLD_FT
        )

        tide_summary = {
            "station_id": NOAA_STATION_ID,
            "station_name": NOAA_STATION_NAME,
            "high_tides": high_tides,
            "low_tides": low_tides,
            "today_high_tides": today_highs,
            "today_low_tides": today_lows,
            "max_high_ft": max_high_ft,
            "min_low_ft": min_low_ft,
            "is_king_tide_window": is_king_tide_window,
        }

        log(
            f"NOAA tides fetched: {len(high_tides)} highs, {len(low_tides)} lows, max={max_high_ft}ft"
        )
        return tide_summary

    except Exception as exc:
        log(f"NOAA tide fetch error: {exc}")
        return {}


def _load_meteor_calendar() -> List[Dict[str, Any]]:
    """Load meteor shower calendar from static JSON file.

    M2: Validates required fields are present in each entry.
    """
    path = os.path.join(CALENDARS_DIR, "meteor_showers.json")
    if not os.path.exists(path):
        log(f"Meteor calendar not found at {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # M2: Validate structure - must be a list
        if not isinstance(data, list):
            log(
                f"Meteor calendar invalid format: expected list, got {type(data).__name__}"
            )
            return []

        # Filter out entries missing required fields
        required_fields = {
            "name",
            "active_start",
            "active_end",
            "peak_start",
            "peak_end",
        }
        valid_entries = []
        for entry in data:
            if isinstance(entry, dict) and required_fields.issubset(entry.keys()):
                valid_entries.append(entry)
            else:
                log(f"Skipping invalid meteor entry: {entry.get('name', 'unknown')}")

        return valid_entries
    except json.JSONDecodeError as exc:
        log(f"Meteor calendar JSON parse error: {exc}")
        return []
    except OSError as exc:
        log(f"Meteor calendar load error: {exc}")
        return []


def _load_moon_events(year: int) -> Dict[str, Dict[str, Any]]:
    """Load named moon events for a given year from static JSON file.

    M2: Validates structure and required fields.
    """
    path = os.path.join(CALENDARS_DIR, f"moon_events_{year}.json")
    if not os.path.exists(path):
        log(f"Moon events calendar not found at {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # M2: Validate structure - must be a dict with date keys
        if not isinstance(data, dict):
            log(f"Moon events invalid format: expected dict, got {type(data).__name__}")
            return {}

        # Validate each entry has at least full_moon_name
        valid_entries = {}
        for date_key, event in data.items():
            if isinstance(event, dict) and "full_moon_name" in event:
                valid_entries[date_key] = event
            else:
                log(f"Skipping invalid moon event for {date_key}")

        return valid_entries
    except json.JSONDecodeError as exc:
        log(f"Moon events JSON parse error: {exc}")
        return {}
    except OSError as exc:
        log(f"Moon events calendar load error: {exc}")
        return {}


def _evaluate_meteor_showers(date_local: datetime) -> Dict[str, Any]:
    """Check if any meteor showers are active or peaking near today."""
    calendar = _load_meteor_calendar()
    if not calendar:
        return {}

    today = date_local.date()
    active_showers = []

    for shower in calendar:
        name = shower.get("name", "Unknown")
        try:
            active_start = (
                datetime.strptime(shower.get("active_start", ""), "%m-%d")
                .date()
                .replace(year=today.year)
            )
            active_end = (
                datetime.strptime(shower.get("active_end", ""), "%m-%d")
                .date()
                .replace(year=today.year)
            )
            peak_start = (
                datetime.strptime(shower.get("peak_start", ""), "%m-%d")
                .date()
                .replace(year=today.year)
            )
            peak_end = (
                datetime.strptime(shower.get("peak_end", ""), "%m-%d")
                .date()
                .replace(year=today.year)
            )
        except (ValueError, TypeError):
            continue

        # Handle year wraparound (e.g., Quadrantids: Dec 28 - Jan 12)
        if active_end < active_start:
            # Shower spans new year
            if today >= active_start or today <= active_end:
                is_active = True
            else:
                is_active = False
        else:
            is_active = active_start <= today <= active_end

        if not is_active:
            continue

        # Check if within ±3 days of peak
        days_to_peak_start = (peak_start - today).days
        days_to_peak_end = (peak_end - today).days
        is_peak_window = (
            -3 <= days_to_peak_start <= 3
            or -3 <= days_to_peak_end <= 3
            or (peak_start <= today <= peak_end)
        )

        active_showers.append(
            {
                "name": name,
                "is_peak_window": is_peak_window,
                "peak_start": peak_start.strftime("%b %d"),
                "peak_end": peak_end.strftime("%b %d"),
                "zhr": shower.get("zhr"),
                "notes": shower.get("notes", ""),
            }
        )

    if not active_showers:
        return {}

    # Pick the most notable (prefer peak window, then highest ZHR)
    active_showers.sort(key=lambda s: (not s["is_peak_window"], -(s.get("zhr") or 0)))
    best = active_showers[0]

    return {
        "meteor_shower_name": best["name"],
        "is_peak_window": best["is_peak_window"],
        "peak_dates": f"{best['peak_start']} - {best['peak_end']}",
        "zhr": best.get("zhr"),
        "notes": best.get("notes"),
        "all_active": [s["name"] for s in active_showers],
    }


def _evaluate_moon_events(
    date_local: datetime, moon_phase: Optional[float] = None
) -> Dict[str, Any]:
    """Check for named moon events on or near today."""
    today_str = date_local.strftime("%Y-%m-%d")
    year = date_local.year

    events = _load_moon_events(year)
    if not events:
        return {}

    # Check today and adjacent days
    result = {}
    for offset in [0, 1, -1]:
        check_date = (date_local + timedelta(days=offset)).strftime("%Y-%m-%d")
        if check_date in events:
            event = events[check_date]
            result = {
                "date": check_date,
                "full_moon_name": event.get("full_moon_name"),
                "is_blue_moon": event.get("is_blue_moon", False),
                "is_supermoon": event.get("is_supermoon", False),
                "notes": event.get("notes", ""),
            }
            # Mark if it's exactly today
            if check_date == today_str:
                result["is_today"] = True
            else:
                result["is_today"] = False
                result["days_away"] = offset
            break

    return result


def get_coast_sky_summary(now_local: Optional[datetime] = None) -> Dict[str, Any]:
    """Get combined coast & sky summary for the current day.

    Returns a dict with optional keys:
    - tide_summary: NOAA tide predictions
    - sky_summary: meteor shower info
    - moon_event_summary: named moon events

    Uses caching to avoid repeated API calls.
    """
    if now_local is None:
        tz = _get_local_tz()
        now_local = datetime.now(tz)

    # Check cache first
    cached = _load_cache()
    if cached:
        return cached

    result: Dict[str, Any] = {}

    # Fetch NOAA tides
    tide_summary = _fetch_noaa_tides(now_local)
    if tide_summary:
        result["tide_summary"] = tide_summary

    # Evaluate meteor showers
    sky_summary = _evaluate_meteor_showers(now_local)
    if sky_summary:
        result["sky_summary"] = sky_summary

    # Evaluate named moon events
    moon_event = _evaluate_moon_events(now_local)
    if moon_event:
        result["moon_event_summary"] = moon_event

    # Cache result
    if result:
        _save_cache(result)

    return result


if __name__ == "__main__":
    # Test run
    log("Testing coast_sky_service...")
    tz = _get_local_tz()
    now = datetime.now(tz)
    log(f"Local time: {now.isoformat()}")

    summary = get_coast_sky_summary(now)
    print(json.dumps(summary, indent=2, default=str))
