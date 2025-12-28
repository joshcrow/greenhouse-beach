"""Greenhouse Gazette Application Package.

This package contains the core application logic including:
- config: Pydantic settings for centralized configuration
- models: Data models for sensors, weather, and email content
- services: Business logic services (future)
"""

from app.config import settings

__all__ = ["settings"]
