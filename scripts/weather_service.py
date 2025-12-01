import os
from datetime import datetime
from typing import Any, Dict, Optional

import requests


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [weather] {message}", flush=True)


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
        "exclude": "minutely,hourly,daily,alerts",
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
        weather_list = current.get("weather", [])
        condition = weather_list[0].get("main") if weather_list else None

        result: Dict[str, Any] = {}
        if "temp" in current:
            result["outdoor_temp"] = float(current["temp"])
        if condition is not None:
            result["condition"] = str(condition)
        if "humidity" in current:
            result["humidity_out"] = int(current["humidity"])

        log(f"Fetched external weather: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        # This will also catch HTTPError (including 401) from raise_for_status.
        log(f"Weather API unreachable or error occurred: {exc}")
        return {}
