#!/usr/bin/env python3
"""Golden Hour Photo Capture for Greenhouse Gazette.

Calculates the optimal photo capture time (golden hour) based on sunset,
and triggers the camera bridge at that time.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple
import requests


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [golden_hour] {message}", flush=True)


def get_sunset_time() -> Optional[datetime]:
    """Fetch today's sunset time from OpenWeather API."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    lat = os.getenv("LAT")
    lon = os.getenv("LON")
    
    if not api_key or not lat or not lon:
        log("Weather API config missing")
        return None
    
    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "exclude": "minutely,hourly,alerts",
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        current = data.get("current", {})
        sunset_ts = current.get("sunset")
        
        if sunset_ts:
            sunset = datetime.fromtimestamp(sunset_ts)
            log(f"Today's sunset: {sunset.strftime('%H:%M')}")
            return sunset
    except Exception as e:
        log(f"Error fetching sunset time: {e}")
    
    return None


def get_golden_hour() -> Optional[datetime]:
    """Calculate golden hour (1 hour before sunset)."""
    sunset = get_sunset_time()
    if not sunset:
        return None
    
    golden = sunset - timedelta(hours=1)
    log(f"Golden hour calculated: {golden.strftime('%H:%M')}")
    return golden


def get_golden_hour_schedule() -> str:
    """Get the golden hour time as HH:MM for scheduler.
    
    Falls back to 4:00 PM if API unavailable.
    """
    golden = get_golden_hour()
    if golden:
        return golden.strftime("%H:%M")
    
    # Fallback: 4:00 PM is usually good for winter golden hour
    log("Using fallback golden hour: 16:00")
    return "16:00"


def should_capture_now(tolerance_minutes: int = 30) -> bool:
    """Check if current time is within golden hour window."""
    golden = get_golden_hour()
    if not golden:
        return False
    
    now = datetime.now()
    diff = abs((now - golden).total_seconds() / 60)
    
    if diff <= tolerance_minutes:
        log(f"Within golden hour window (±{tolerance_minutes}min)")
        return True
    return False


# Default golden hour times by month (for Outer Banks, NC ~36°N)
# These are approximate times for 1 hour before sunset
SEASONAL_GOLDEN_HOURS = {
    1: "16:00",   # January - sunset ~5:15 PM
    2: "16:30",   # February
    3: "17:15",   # March (DST starts)
    4: "18:45",   # April
    5: "19:15",   # May
    6: "19:30",   # June - longest days
    7: "19:30",   # July
    8: "19:00",   # August
    9: "18:15",   # September
    10: "17:30",  # October
    11: "15:45",  # November (DST ends)
    12: "15:45",  # December - shortest days
}


def get_seasonal_golden_hour() -> str:
    """Get golden hour based on current month (no API needed)."""
    month = datetime.now().month
    return SEASONAL_GOLDEN_HOURS.get(month, "16:30")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sunset", action="store_true", help="Show today's sunset time")
    parser.add_argument("--golden", action="store_true", help="Show golden hour time")
    parser.add_argument("--seasonal", action="store_true", help="Show seasonal golden hour")
    parser.add_argument("--check", action="store_true", help="Check if now is golden hour")
    args = parser.parse_args()
    
    if args.sunset:
        sunset = get_sunset_time()
        if sunset:
            print(f"Sunset: {sunset.strftime('%H:%M')}")
    elif args.golden:
        golden = get_golden_hour()
        if golden:
            print(f"Golden hour: {golden.strftime('%H:%M')}")
    elif args.seasonal:
        print(f"Seasonal golden hour: {get_seasonal_golden_hour()}")
    elif args.check:
        if should_capture_now():
            print("Yes - capture now!")
        else:
            print("No - not golden hour")
    else:
        print("Usage: golden_hour.py [--sunset | --golden | --seasonal | --check]")
