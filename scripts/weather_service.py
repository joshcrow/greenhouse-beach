import os
from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from utils.logger import create_logger

log = create_logger("weather")

# Lazy settings loader for app.config integration
_settings = None

def _get_settings():
    """Get settings lazily to avoid import-time failures."""
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception:
            _settings = None
    return _settings


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
    # OpenWeather's wind_deg is the direction the wind is COMING FROM.
    # For display, we want the arrow to show where the wind is blowing TOWARD.
    deg_to = (deg + 180.0) % 360.0
    idx = int((deg_to % 360) / 45.0 + 0.5) % 8
    return arrows[idx]


def _format_local_time(unix_seconds: float) -> str:
    cfg = _get_settings()
    tz_name = cfg.tz if cfg else (os.getenv("TZ") or "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    dt = datetime.fromtimestamp(float(unix_seconds), tz=tz)
    return dt.strftime("%I:%M %p").lstrip("0")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.RequestException, requests.Timeout)),
    reraise=False,
)
def _fetch_weather_data(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Internal function to fetch weather data with retry logic."""
    resp = requests.get(url, params=params, timeout=5)
    resp.raise_for_status()
    return resp.json()


def get_current_weather() -> Dict[str, Any]:
    """Fetch current weather from OpenWeatherMap.

    Returns a dict like:
    {"outdoor_temp": 45.2, "condition": "Light Rain", "humidity_out": 88}
    or {} on failure. Never raises.
    
    Uses tenacity retry with exponential backoff for network resilience.
    """

    cfg = _get_settings()
    api_key = cfg.openweather_api_key if cfg else os.getenv("OPENWEATHER_API_KEY")
    lat = cfg.lat if cfg else os.getenv("LAT")
    lon = cfg.lon if cfg else os.getenv("LON")
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
            from urllib.parse import (
                urlencode,
            )  # local import to avoid global dependency

            redacted_params = dict(params)
            if "appid" in redacted_params:
                redacted_params["appid"] = "***REDACTED***"
            redacted_query = urlencode(redacted_params)
            redacted_url = f"{url}?{redacted_query}"
            log(f"Calling OpenWeather API: {redacted_url}")
        except Exception:
            # If URL building fails, continue without logging the full URL
            log("Calling OpenWeather API (URL redacted)")

        data = _fetch_weather_data(url, params)
        if data is None:
            log("Weather API request failed after retries")
            return {}

        current = data.get("current", {})
        daily_list = data.get("daily", [])
        weather_list = current.get("weather", [])
        condition = weather_list[0].get("main") if weather_list else None

        result: Dict[str, Any] = {}

        # Current conditions (round to integers for cleaner display)
        if "temp" in current:
            result["outdoor_temp"] = round(float(current["temp"]))
        if condition is not None:
            result["condition"] = str(condition)
        if "humidity" in current:
            result["humidity_out"] = round(float(current["humidity"]))

        # Cloud cover and pressure (for visibility gating and storm context)
        if "clouds" in current:
            result["clouds_pct"] = round(float(current["clouds"]))
        if "pressure" in current:
            result["pressure_hpa"] = round(float(current["pressure"]))

        # Wind (round to integers)
        if "wind_speed" in current:
            result["wind_mph"] = round(float(current["wind_speed"]))
        if "wind_deg" in current:
            deg = float(current["wind_deg"])
            result["wind_deg"] = deg
            result["wind_direction"] = _wind_direction(deg)
            result["wind_arrow"] = _wind_arrow(deg)

        # Rain volume (mm -> inches) for septic/runoff logic
        # OpenWeather 3.0 provides daily rain total in daily[0].rain (mm)
        if daily_list:
            first_day = daily_list[0] or {}
            if "rain" in first_day:
                rain_mm = float(first_day["rain"])
                result["rain_last_24h_mm"] = round(rain_mm, 1)
                result["rain_last_24h_in"] = round(rain_mm / 25.4, 2)

        # Daily high/low and moon phase (use first daily entry, round to integers)
        if daily_list:
            first = daily_list[0] or {}
            temp_block = first.get("temp", {})
            if "max" in temp_block:
                result["high_temp"] = round(float(temp_block["max"]))
            if "min" in temp_block:
                result["low_temp"] = round(float(temp_block["min"]))
            if "moon_phase" in first:
                phase = float(first["moon_phase"])
                result["moon_phase"] = phase
                result["moon_icon"] = _moon_phase_icon(phase)

            if "sunrise" in first:
                result["sunrise"] = _format_local_time(float(first["sunrise"]))
            elif "sunrise" in current:
                result["sunrise"] = _format_local_time(float(current["sunrise"]))
            if "sunset" in first:
                result["sunset"] = _format_local_time(float(first["sunset"]))
            elif "sunset" in current:
                result["sunset"] = _format_local_time(float(current["sunset"]))

            # Daily wind (more representative for "Today's Weather" summary, round to integers)
            if "wind_speed" in first:
                result["daily_wind_mph"] = round(float(first["wind_speed"]))
            if "wind_deg" in first:
                result["daily_wind_deg"] = float(first["wind_deg"])
                result["daily_wind_direction"] = _wind_direction(
                    result["daily_wind_deg"]
                )
                result["daily_wind_arrow"] = _wind_arrow(result["daily_wind_deg"])

            # Precipitation probability (for meteor shower visibility gating)
            if "pop" in first:
                result["precip_prob"] = round(
                    float(first["pop"]) * 100
                )  # Convert 0-1 to 0-100%

        # Tomorrow's forecast (lookahead for narrative, round to integers)
        if len(daily_list) > 1:
            tomorrow = daily_list[1] or {}
            tomorrow_temp = tomorrow.get("temp", {})
            if "max" in tomorrow_temp:
                result["tomorrow_high"] = round(float(tomorrow_temp["max"]))
            if "min" in tomorrow_temp:
                result["tomorrow_low"] = round(float(tomorrow_temp["min"]))
            tomorrow_weather = tomorrow.get("weather", [])
            if tomorrow_weather:
                result["tomorrow_condition"] = str(tomorrow_weather[0].get("main", ""))

        log(f"Fetched external weather: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        # This will also catch HTTPError (including 401) from raise_for_status.
        log(f"Weather API unreachable or error occurred: {exc}")
        return {}
