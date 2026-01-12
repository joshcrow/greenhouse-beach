"""Jinja2 email template rendering for Greenhouse Gazette.

This module provides template rendering for email generation,
replacing the inline HTML in publisher.py.

Usage:
    from email_templates import render_daily_email
    
    html = render_daily_email(
        subject="Clear Skies",
        headline="A quiet day",
        body_html="<p>Inside is 68°.</p>",
        interior_temp=68,
        ...
    )
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from utils.logger import create_logger

log = create_logger("templates")

# Template directory (relative to project root)
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _get_jinja_env() -> Environment:
    """Create and configure Jinja2 environment."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def render_daily_email(
    # Core content
    subject: str,
    headline: str,
    body_html: str,
    date_display: str,
    # Sensor data
    interior_temp: Optional[int] = None,
    interior_humidity: Optional[int] = None,
    interior_stale: bool = False,
    exterior_temp: Optional[int] = None,
    exterior_humidity: Optional[int] = None,
    exterior_stale: bool = False,
    # Weather details
    condition: str = "",
    condition_emoji: str = "",
    high_temp: Optional[int] = None,
    low_temp: Optional[int] = None,
    wind_display: str = "",
    sunrise: str = "",
    sunset: str = "",
    moon_icon: str = "",
    moon_phase: str = "",
    tide_display: str = "",
    # Optional sections
    image_cid: Optional[str] = None,
    chart_cid: Optional[str] = None,
    stats_24h: Optional[Dict[str, Any]] = None,
    riddle_text: Optional[str] = None,
    yesterday_answer: Optional[str] = None,
    riddle_date: Optional[str] = None,
    bot_email: Optional[str] = None,
    yesterdays_winners: Optional[List[str]] = None,
    leaderboard: Optional[List[Dict[str, Any]]] = None,
    alerts: Optional[List[Dict[str, str]]] = None,
    # Weekly mode (Sunday edition)
    weekly_mode: bool = False,
    weekly_stats: Optional[Dict[str, Any]] = None,
    # Debug/test mode
    test_mode: bool = False,
    debug_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Render the daily email HTML using Jinja2 templates.
    
    Args:
        subject: Email subject line
        headline: Main headline text
        body_html: Narrative body (HTML formatted)
        date_display: Formatted date string (e.g., "Monday, January 5, 2026")
        interior_temp: Greenhouse temperature (°F)
        interior_humidity: Greenhouse humidity (%)
        interior_stale: Whether interior data is stale
        exterior_temp: Outside temperature (°F)
        exterior_humidity: Outside humidity (%)
        exterior_stale: Whether exterior data is stale
        condition: Weather condition text (e.g., "Clear")
        condition_emoji: Emoji for condition
        high_temp: Forecast high (°F)
        low_temp: Forecast low (°F)
        wind_display: Formatted wind string (e.g., "💨 NE 12 mph")
        sunrise: Sunrise time string
        sunset: Sunset time string
        moon_icon: Moon phase emoji
        moon_phase: Moon phase name
        tide_display: Formatted tide string
        chart_cid: CID for embedded temperature chart image
        riddle_text: Today's riddle (optional)
        yesterday_answer: Yesterday's riddle answer (optional)
        alerts: List of alert dicts with 'icon', 'title', 'detail' keys
    
    Returns:
        Rendered HTML string
    """
    env = _get_jinja_env()
    template = env.get_template("daily_email.html")
    
    html = template.render(
        subject=subject,
        headline=headline,
        body_html=body_html,
        date_display=date_display,
        interior_temp=interior_temp,
        interior_humidity=interior_humidity,
        interior_stale=interior_stale,
        exterior_temp=exterior_temp,
        exterior_humidity=exterior_humidity,
        exterior_stale=exterior_stale,
        condition=condition,
        condition_emoji=condition_emoji,
        high_temp=high_temp,
        low_temp=low_temp,
        wind_display=wind_display,
        sunrise=sunrise,
        sunset=sunset,
        moon_icon=moon_icon,
        moon_phase=moon_phase,
        tide_display=tide_display,
        image_cid=image_cid,
        chart_cid=chart_cid,
        stats_24h=stats_24h,
        riddle_text=riddle_text,
        yesterday_answer=yesterday_answer,
        riddle_date=riddle_date,
        bot_email=bot_email,
        yesterdays_winners=yesterdays_winners or [],
        leaderboard=leaderboard or [],
        alerts=alerts or [],
        weekly_mode=weekly_mode,
        weekly_stats=weekly_stats,
        test_mode=test_mode,
        debug_info=debug_info,
    )
    
    log(f"Rendered daily email template ({len(html)} chars)")
    return html


def get_condition_emoji(condition: Optional[str]) -> str:
    """Get emoji for weather condition."""
    if not condition:
        return "🌤️"
    
    condition_lower = condition.lower()
    emoji_map = {
        "clear": "☀️",
        "sunny": "☀️",
        "clouds": "☁️",
        "cloudy": "☁️",
        "partly": "⛅",
        "overcast": "☁️",
        "rain": "🌧️",
        "drizzle": "🌦️",
        "thunderstorm": "⛈️",
        "snow": "🌨️",
        "mist": "🌫️",
        "fog": "🌫️",
        "haze": "🌫️",
    }
    
    for key, emoji in emoji_map.items():
        if key in condition_lower:
            return emoji
    
    return "🌤️"


def format_wind(wind_mph: Optional[int], wind_direction: str = "", wind_arrow: str = "") -> str:
    """Format wind display string."""
    if wind_mph is None:
        return "💨 --"
    
    if wind_direction and wind_arrow:
        return f"💨 {wind_direction} {wind_arrow} {wind_mph} mph"
    elif wind_direction:
        return f"💨 {wind_direction} {wind_mph} mph"
    else:
        return f"💨 {wind_mph} mph"


def format_moon_phase(moon_phase: Optional[float]) -> str:
    """Get moon phase name from phase value (0-1)."""
    if moon_phase is None:
        return "Unknown"
    
    if moon_phase < 0.03 or moon_phase >= 0.97:
        return "New Moon"
    elif moon_phase < 0.22:
        return "Waxing Crescent"
    elif moon_phase < 0.28:
        return "First Quarter"
    elif moon_phase < 0.47:
        return "Waxing Gibbous"
    elif moon_phase < 0.53:
        return "Full Moon"
    elif moon_phase < 0.72:
        return "Waning Gibbous"
    elif moon_phase < 0.78:
        return "Last Quarter"
    else:
        return "Waning Crescent"
