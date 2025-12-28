"""Greenhouse Gazette Application Package.

This package contains the core application logic including:
- config: Pydantic settings for centralized configuration
- models: Data models for sensors, weather, and email content
- services: Business logic services (future)
"""

from app.config import settings
from app.models import (
    EmailContent,
    SensorReading,
    SensorSnapshot,
    SkySummary,
    Stats24h,
    TideEvent,
    TideSummary,
    WeatherData,
    WeeklySummary,
)

__all__ = [
    "settings",
    "EmailContent",
    "SensorReading",
    "SensorSnapshot",
    "SkySummary",
    "Stats24h",
    "TideEvent",
    "TideSummary",
    "WeatherData",
    "WeeklySummary",
]
