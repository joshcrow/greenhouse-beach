import os
from datetime import datetime
from typing import Any, Dict, Optional

import requests


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [weather] {message}", flush=True)


def _moon_phase_icon(phase: float) -> str:
    """Return a simple Unicode icon for the moon phase (0-1)."""
    # Based on OpenWeather docs: 0 and 1 are new moon, 0.5 full moon.
    if phase < 0.125 or phase >= 0.875:
        return "🌑"  # new
    if phase < 0.25:
        return "🌒"  # waxing crescent
    if phase < 0.375:
        return "🌓"  # first quarter
    if phase < 0.5:
        return "🌔"  # waxing gibbous
    if phase < 0.625:
        return "🌕"  # full
    if phase < 0.75:
        return "🌖"  # waning gibbous
    if phase < 0.875:
        return "🌗"  # last quarter
    return "🌘"  # waning crescent


def _wind_direction(deg: float) -> str:
    """Return a compass direction like N, NE, E, ... for wind degrees."""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((deg % 360) / 45.0 + 0.5) % 8
    return dirs[idx]


def _wind_arrow(deg: float) -> str:
    """Return a Unicode arrow indicating wind direction."""
    arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
    idx = int((deg % 360) / 45.0 + 0.5) % 8
    return arrows[idx]


def get_current_weather() -> Dict[str, Any]:
    """Fetch current weather from OpenWeatherMap.

    Returns a dict like:
    {"outdoor_temp": 45.2, "condition": "Light Rain", "humidity_out": 88}
    or {} on failure. Never raises.
    """

    api_key = os.getenv("OPENWEATHER_API_KEY")
    lat = os.getenv("LAT")
    lon = os.getenv("LON")
    units = os.getenv("WEATHER_UNITS", "imperial")  # 'imperial' gives Fahrenheit

    if not api_key or not lat or not lon:
        log("Weather API config missing (OPENWEATHER_API_KEY, LAT, or LON); skipping.")
        return {}

    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": units,
        "exclude": "minutely,hourly,alerts",
    }

    try:
        # Build a redacted URL string for logging (never expose the API key)
        try:
            from urllib.parse import urlencode  # local import to avoid global dependency

            redacted_params = dict(params)
            if "appid" in redacted_params:
                redacted_params["appid"] = "***REDACTED***"
            redacted_query = urlencode(redacted_params)
            redacted_url = f"{url}?{redacted_query}"
            log(f"Calling OpenWeather API: {redacted_url}")
        except Exception:
            # If URL building fails, continue without logging the full URL
            log("Calling OpenWeather API (URL redacted)")

        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        daily_list = data.get("daily", [])
        weather_list = current.get("weather", [])
        condition = weather_list[0].get("main") if weather_list else None

        result: Dict[str, Any] = {}

        # Current conditions
        if "temp" in current:
            result["outdoor_temp"] = float(current["temp"])
        if condition is not None:
            result["condition"] = str(condition)
        if "humidity" in current:
            result["humidity_out"] = int(current["humidity"])

        # Wind
        if "wind_speed" in current:
            result["wind_mph"] = float(current["wind_speed"])
        if "wind_deg" in current:
            deg = float(current["wind_deg"])
            result["wind_deg"] = deg
            result["wind_direction"] = _wind_direction(deg)
            result["wind_arrow"] = _wind_arrow(deg)

        # Daily high/low and moon phase (use first daily entry)
        if daily_list:
            first = daily_list[0] or {}
            temp_block = first.get("temp", {})
            if "max" in temp_block:
                result["high_temp"] = float(temp_block["max"])
            if "min" in temp_block:
                result["low_temp"] = float(temp_block["min"])
            if "moon_phase" in first:
                phase = float(first["moon_phase"])
                result["moon_phase"] = phase
                result["moon_icon"] = _moon_phase_icon(phase)
            
            # Daily wind (more representative for "Today's Weather" summary)
            if "wind_speed" in first:
                result["daily_wind_mph"] = float(first["wind_speed"])
            if "wind_deg" in first:
                result["daily_wind_deg"] = float(first["wind_deg"])
                result["daily_wind_direction"] = _wind_direction(result["daily_wind_deg"])
                result["daily_wind_arrow"] = _wind_arrow(result["daily_wind_deg"])
        
        # Tomorrow's forecast (lookahead for narrative)
        if len(daily_list) > 1:
            tomorrow = daily_list[1] or {}
            tomorrow_temp = tomorrow.get("temp", {})
            if "max" in tomorrow_temp:
                result["tomorrow_high"] = float(tomorrow_temp["max"])
            if "min" in tomorrow_temp:
                result["tomorrow_low"] = float(tomorrow_temp["min"])
            tomorrow_weather = tomorrow.get("weather", [])
            if tomorrow_weather:
                result["tomorrow_condition"] = str(tomorrow_weather[0].get("main", ""))

        log(f"Fetched external weather: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        # This will also catch HTTPError (including 401) from raise_for_status.
        log(f"Weather API unreachable or error occurred: {exc}")
        return {}
