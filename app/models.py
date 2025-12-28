"""Pydantic data models for the Greenhouse Gazette.

These models provide type-safe data structures replacing raw dictionaries,
enabling better IDE support, validation, and self-documentation.

Usage:
    from app.models import SensorSnapshot, WeatherData, EmailContent
    
    snapshot = SensorSnapshot.from_status_dict(raw_data, last_seen)
    weather = WeatherData(**api_response)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class SensorReading(BaseModel):
    """A single sensor reading with metadata."""
    
    value: Optional[float] = None
    is_stale: bool = False
    last_seen: Optional[datetime] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if reading has a valid, non-stale value."""
        return self.value is not None and not self.is_stale
    
    def __str__(self) -> str:
        if self.value is None:
            return "N/A"
        if self.is_stale:
            return f"{self.value:.1f} (STALE)"
        return f"{self.value:.1f}"


class SensorSnapshot(BaseModel):
    """Current state of all greenhouse sensors.
    
    This model handles the sensor remapping logic:
    - exterior_* keys → interior (main greenhouse sensor)
    - satellite-2_* keys → exterior (outside weather)
    - interior_* keys → suppressed (broken hardware)
    """
    
    # Interior sensors (remapped from exterior_* keys)
    interior_temp: Optional[SensorReading] = None
    interior_humidity: Optional[SensorReading] = None
    
    # Exterior sensors (remapped from satellite-2_* keys)
    exterior_temp: Optional[SensorReading] = None
    exterior_humidity: Optional[SensorReading] = None
    
    # Satellite battery
    satellite_battery: Optional[SensorReading] = None
    
    # Raw timestamp for debugging
    updated_at: Optional[datetime] = None
    
    @classmethod
    def from_status_dict(
        cls,
        sensors: Dict[str, Any],
        last_seen: Dict[str, str],
        stale_threshold_hours: float = 2.0,
    ) -> "SensorSnapshot":
        """Factory method to create snapshot from raw status.json data.
        
        Implements the sensor remapping logic from publisher.py:
        - exterior_* → interior (physical reality mapping)
        - satellite-2_* → exterior
        - interior_* → suppressed (broken hardware)
        
        Args:
            sensors: Raw sensor values dict
            last_seen: Dict of sensor key → ISO timestamp
            stale_threshold_hours: Hours after which data is considered stale
        """
        def check_stale(key: str) -> bool:
            """Check if sensor data is stale."""
            if key not in last_seen:
                return True
            try:
                ts_str = last_seen[key]
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                age = datetime.now(ts.tzinfo) - ts
                return age.total_seconds() > (stale_threshold_hours * 3600)
            except (ValueError, TypeError):
                return True
        
        def make_reading(raw_key: str) -> Optional[SensorReading]:
            """Create a SensorReading from raw data."""
            if raw_key not in sensors:
                return None
            value = sensors.get(raw_key)
            if value is None:
                return None
            try:
                return SensorReading(
                    value=float(value),
                    is_stale=check_stale(raw_key),
                    last_seen=datetime.fromisoformat(
                        last_seen.get(raw_key, "").replace("Z", "+00:00")
                    ) if raw_key in last_seen else None,
                )
            except (ValueError, TypeError):
                return None
        
        return cls(
            # Remap exterior_* → interior (physical sensor location swap)
            interior_temp=make_reading("exterior_temp"),
            interior_humidity=make_reading("exterior_humidity"),
            # Remap satellite-2_* → exterior
            exterior_temp=make_reading("satellite-2_temperature"),
            exterior_humidity=make_reading("satellite-2_humidity"),
            # Battery (keep original key)
            satellite_battery=make_reading("satellite-2_battery"),
            updated_at=datetime.utcnow(),
        )
    
    def to_narrator_dict(self) -> Dict[str, Any]:
        """Convert to dict format expected by narrator.generate_update().
        
        Returns dict with values set to None for stale readings,
        so AI doesn't write narratives based on old data.
        """
        result: Dict[str, Any] = {}
        
        if self.interior_temp:
            result["interior_temp"] = self.interior_temp.value if self.interior_temp.is_valid else None
            if self.interior_temp.is_stale:
                result["interior_temp_stale"] = True
        
        if self.interior_humidity:
            result["interior_humidity"] = self.interior_humidity.value if self.interior_humidity.is_valid else None
            if self.interior_humidity.is_stale:
                result["interior_humidity_stale"] = True
        
        if self.exterior_temp:
            result["exterior_temp"] = self.exterior_temp.value if self.exterior_temp.is_valid else None
            if self.exterior_temp.is_stale:
                result["exterior_temp_stale"] = True
        
        if self.exterior_humidity:
            result["exterior_humidity"] = self.exterior_humidity.value if self.exterior_humidity.is_valid else None
            if self.exterior_humidity.is_stale:
                result["exterior_humidity_stale"] = True
        
        if self.satellite_battery:
            result["satellite-2_battery"] = self.satellite_battery.value
            if self.satellite_battery.is_stale:
                result["satellite-2_battery_stale"] = True
        
        return result


class WeatherData(BaseModel):
    """Weather data from OpenWeatherMap API."""
    
    # Current conditions
    outdoor_temp: Optional[int] = None
    condition: Optional[str] = None
    humidity_out: Optional[int] = None
    clouds_pct: Optional[int] = None
    pressure_hpa: Optional[int] = None
    
    # Wind
    wind_mph: Optional[int] = None
    wind_deg: Optional[float] = None
    wind_direction: Optional[str] = None
    wind_arrow: Optional[str] = None
    
    # Daily forecast
    high_temp: Optional[int] = None
    low_temp: Optional[int] = None
    daily_wind_mph: Optional[int] = None
    daily_wind_deg: Optional[float] = None
    daily_wind_direction: Optional[str] = None
    daily_wind_arrow: Optional[str] = None
    precip_prob: Optional[int] = None
    
    # Tomorrow forecast
    tomorrow_high: Optional[int] = None
    tomorrow_low: Optional[int] = None
    tomorrow_condition: Optional[str] = None
    
    # Astronomy
    moon_phase: Optional[float] = None
    moon_icon: Optional[str] = None
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "WeatherData":
        """Create from weather_service.get_current_weather() response."""
        return cls(**{k: v for k, v in data.items() if k in cls.model_fields})


class TideEvent(BaseModel):
    """A single tide event (high or low)."""
    
    time_local: str
    height_ft: float
    
    @property
    def time_display(self) -> str:
        """Format time for display (HH:MM AM/PM)."""
        try:
            dt = datetime.fromisoformat(self.time_local)
            return dt.strftime("%-I:%M %p")
        except (ValueError, TypeError):
            return "N/A"


class TideSummary(BaseModel):
    """Tide data from NOAA."""
    
    station_id: str
    station_name: str
    high_tides: List[TideEvent] = Field(default_factory=list)
    low_tides: List[TideEvent] = Field(default_factory=list)
    today_high_tides: List[TideEvent] = Field(default_factory=list)
    today_low_tides: List[TideEvent] = Field(default_factory=list)
    max_high_ft: Optional[float] = None
    min_low_ft: Optional[float] = None
    is_king_tide_window: bool = False


class SkySummary(BaseModel):
    """Sky events (meteor showers, moon events)."""
    
    meteor_shower_name: Optional[str] = None
    is_peak_window: bool = False
    peak_dates: Optional[str] = None
    zhr: Optional[int] = None
    notes: Optional[str] = None
    all_active: List[str] = Field(default_factory=list)


class EmailContent(BaseModel):
    """Content for the daily/weekly email."""
    
    subject: str
    headline: str
    body_html: str
    body_plain: str
    is_weekly: bool = False
    
    # Optional metadata
    narrator_model: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class WeeklySummary(BaseModel):
    """Weekly statistics summary for Sunday edition."""
    
    days_recorded: int = 0
    week_start: Optional[str] = None
    week_end: Optional[str] = None
    temp_min: Optional[int] = None
    temp_max: Optional[int] = None
    temp_avg: Optional[int] = None
    humidity_min: Optional[int] = None
    humidity_max: Optional[int] = None
    humidity_avg: Optional[int] = None


class Stats24h(BaseModel):
    """24-hour min/max statistics."""
    
    interior_temp_min: Optional[float] = None
    interior_temp_max: Optional[float] = None
    interior_humidity_min: Optional[float] = None
    interior_humidity_max: Optional[float] = None
    exterior_temp_min: Optional[float] = None
    exterior_temp_max: Optional[float] = None
    exterior_humidity_min: Optional[float] = None
    exterior_humidity_max: Optional[float] = None
    
    @classmethod
    def from_stats_dict(cls, data: Dict[str, Any]) -> "Stats24h":
        """Create from stats.get_24h_stats() response."""
        return cls(**{k: v for k, v in data.items() if k in cls.model_fields})
