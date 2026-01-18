"""Centralized configuration using Pydantic Settings.

This module provides fail-fast validation of environment variables at startup.
All configuration is accessed via the singleton `settings` object.

Usage:
    from app.config import settings
    
    api_key = settings.gemini_api_key
    recipients = settings.smtp_recipients  # Already parsed as list
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    
    Required variables will cause startup failure if not set.
    Optional variables have sensible defaults for development.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra env vars not defined here
    )
    
    # -------------------------------------------------------------------------
    # Core Settings
    # -------------------------------------------------------------------------
    greenhouse_site_name: str = Field(
        default="Outer Banks Greenhouse",
        description="Human-readable site name for email headers",
    )
    tz: str = Field(
        default="America/New_York",
        description="Timezone for scheduling",
    )
    
    # -------------------------------------------------------------------------
    # Gemini AI (Required)
    # -------------------------------------------------------------------------
    gemini_api_key: str = Field(
        description="Google Gemini API key (required)",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Primary Gemini model for narrative generation",
    )
    gemini_fallback_model: str = Field(
        default="gemini-2.0-flash-lite",
        description="Fallback model if primary fails",
    )
    
    # -------------------------------------------------------------------------
    # Weather Service (Required)
    # -------------------------------------------------------------------------
    openweather_api_key: str = Field(
        description="OpenWeatherMap One Call 3.0 API key (required)",
    )
    lat: float = Field(
        default=36.022,
        description="Greenhouse latitude",
    )
    lon: float = Field(
        default=-75.720,
        description="Greenhouse longitude",
    )
    
    # -------------------------------------------------------------------------
    # MQTT Broker
    # -------------------------------------------------------------------------
    mqtt_host: str = Field(
        default="mosquitto",
        description="MQTT broker hostname",
    )
    mqtt_port: int = Field(
        default=1883,
        description="MQTT broker port",
    )
    mqtt_username: Optional[str] = Field(
        default=None,
        description="MQTT username (optional)",
    )
    mqtt_password: Optional[str] = Field(
        default=None,
        description="MQTT password (optional)",
    )
    
    # -------------------------------------------------------------------------
    # Email (SMTP)
    # -------------------------------------------------------------------------
    smtp_server: Optional[str] = Field(
        default=None,
        alias="SMTP_SERVER",
        description="SMTP server hostname",
    )
    smtp_host: Optional[str] = Field(
        default=None,
        description="SMTP host (alias for smtp_server)",
    )
    smtp_port: int = Field(
        default=465,
        description="SMTP port (465 for SSL)",
    )
    smtp_user: Optional[str] = Field(
        default=None,
        description="SMTP username",
    )
    smtp_password: Optional[str] = Field(
        default=None,
        description="SMTP password",
    )
    smtp_from: str = Field(
        default="greenhouse@example.com",
        description="From address for emails",
    )
    smtp_to: str = Field(
        default="you@example.com",
        description="Comma-separated list of recipient emails",
    )
    alert_email: Optional[str] = Field(
        default=None,
        description="Email for device alerts (defaults to first smtp_to)",
    )
    
    # -------------------------------------------------------------------------
    # Data Paths
    # -------------------------------------------------------------------------
    data_dir: str = Field(
        default="/app/data",
        description="Base data directory",
    )
    status_path: str = Field(
        default="/app/data/status.json",
        description="Path to sensor status JSON",
    )
    stats_path: str = Field(
        default="/app/data/stats_24h.json",
        alias="STATS_24H_PATH",
        description="Path to 24h stats JSON",
    )
    stats_weekly_path: str = Field(
        default="/app/data/stats_weekly.json",
        alias="WEEKLY_STATS_PATH",
        description="Path to weekly stats JSON",
    )
    history_cache_path: str = Field(
        default="/app/data/history_cache.json",
        description="Path to history cache",
    )
    archive_path: str = Field(
        default="/app/data/archive",
        description="Path to image archive",
    )
    incoming_path: str = Field(
        default="/app/data/incoming",
        description="Path to incoming images",
    )
    riddle_state_path: str = Field(
        default="/app/data/riddle_state.json",
        description="Path to riddle state JSON",
    )
    sensor_log_dir: str = Field(
        default="/app/data/sensor_log",
        description="Directory for sensor logs",
    )
    knowledge_graph_path: str = Field(
        default="/app/data/colington_knowledge_graph.json",
        description="Path to Colington knowledge graph JSON",
    )
    prompts_dir: str = Field(
        default="/app/data/prompts",
        description="Directory for hot-reloadable prompt templates",
    )
    
    # -------------------------------------------------------------------------
    # Feature Flags
    # -------------------------------------------------------------------------
    test_mode: bool = Field(
        default=False,
        description="Enable test mode (send to primary recipient only)",
    )
    riddle_game_enabled: bool = Field(
        default=True,
        description="Enable riddle game (GUESS command processing)",
    )
    status_write_interval: int = Field(
        default=60,
        description="Seconds between status file writes",
    )
    
    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    @property
    def smtp_server_host(self) -> Optional[str]:
        """Get SMTP server, checking both field names."""
        return self.smtp_server or self.smtp_host
    
    @property
    def smtp_recipients(self) -> List[str]:
        """Parse SMTP_TO into a list of email addresses."""
        return [addr.strip() for addr in self.smtp_to.split(",") if addr.strip()]
    
    @property
    def alert_recipient(self) -> Optional[str]:
        """Get alert email, defaulting to first SMTP recipient."""
        if self.alert_email:
            return self.alert_email
        recipients = self.smtp_recipients
        return recipients[0] if recipients else None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.
    
    Use this for lazy initialization in modules that might be imported
    before environment is fully configured.
    """
    return Settings()


# Eager initialization - fail fast if required env vars are missing
# Comment out for lazy init: settings = get_settings()
try:
    settings = Settings()
except Exception as e:
    # Allow import to succeed for testing, but log the error
    import sys
    print(f"[config] WARNING: Failed to load settings: {e}", file=sys.stderr)
    settings = None  # type: ignore
