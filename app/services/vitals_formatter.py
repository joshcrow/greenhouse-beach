"""Vitals formatting utilities for email display.

Extracts the formatting functions from publisher.py's build_email() function
for better testability and reusability.
"""

from datetime import datetime
from typing import Any, Dict, Optional


class VitalsFormatter:
    """Formats sensor and weather data for email display.
    
    Provides consistent formatting across the email template with
    support for stale data indicators and color coding.
    """
    
    def __init__(self, sensor_data: Dict[str, Any]):
        """Initialize formatter with sensor data for stale checks.
        
        Args:
            sensor_data: Dict containing sensor values and *_stale flags
        """
        self.sensor_data = sensor_data
    
    def fmt(self, value: Any, stale_flag: Optional[str] = None) -> str:
        """Format value for display as integer, returning N/A for None.
        
        Args:
            value: The sensor value to format
            stale_flag: Optional key to check for staleness in sensor_data
        """
        if value is None:
            return "N/A"
        try:
            formatted = str(round(float(value)))
            if stale_flag and self.sensor_data.get(stale_flag):
                formatted += " <span style='color:#ca8a04;'>(STALE)</span>"
            return formatted
        except (ValueError, TypeError):
            return str(value)
    
    def fmt_battery(self, voltage: Any, stale_flag: Optional[str] = None) -> str:
        """Format battery voltage with color coding based on level.
        
        Battery levels (LiPo):
        - 4.2V = Full (100%)
        - 3.7V = Nominal (50%)
        - 3.4V = Low (20%) - yellow warning
        - 3.0V = Critical (5%) - red alert
        - <3.0V = Dead - red, needs immediate charge
        - Stale data = OFFLINE - gray
        """
        if stale_flag and self.sensor_data.get(stale_flag):
            return '<span style="color:#9ca3af;">⚠️ OFFLINE</span>'
        
        if voltage is None:
            return "—"
        
        v = float(voltage)
        if v >= 3.7:
            color = "#16a34a"  # Green - good
            icon = "🔋"
        elif v >= 3.4:
            color = "#ca8a04"  # Yellow - low
            icon = "🪫"
        else:
            color = "#dc2626"  # Red - critical
            icon = "🪫"
        return f'<span style="color:{color};">{icon} {v:.1f}V</span>'
    
    def fmt_temp_high_low(self, high_val: Any, low_val: Any) -> str:
        """Format high/low temps with red/blue color styling."""
        if high_val is None and low_val is None:
            return "N/A"
        high_str = (
            f'<span style="color:#dc2626;" class="dark-text-high">{self.fmt(high_val)}°</span>'
            if high_val is not None
            else "N/A"
        )
        low_str = (
            f'<span style="color:#2563eb;" class="dark-text-low">{self.fmt(low_val)}°</span>'
            if low_val is not None
            else "N/A"
        )
        return f"{high_str} / {low_str}"
    
    def fmt_temp_range(self, high_temp: Any, low_temp: Any) -> str:
        """Format high/low temp range with color styling."""
        if high_temp is None and low_temp is None:
            return "N/A"
        high_str = (
            f'<span style="color:#dc2626;" class="dark-text-high">{high_temp}°</span>'
            if high_temp is not None
            else "N/A"
        )
        low_str = (
            f'<span style="color:#2563eb;" class="dark-text-low">{low_temp}°</span>'
            if low_temp is not None
            else "N/A"
        )
        return f"{high_str} / {low_str}"
    
    def fmt_time(self, value: Any) -> str:
        """Format time value for display."""
        if value is None:
            return "N/A"
        return str(value)
    
    def fmt_wind(
        self,
        wind_mph: Any,
        wind_direction: Optional[str] = None,
        wind_arrow: Optional[str] = None,
    ) -> str:
        """Format wind display, handling calm conditions."""
        if wind_mph is None:
            return "N/A"
        speed = round(float(wind_mph))
        if speed < 1:
            return "Calm"
        direction = wind_direction or "N/A"
        arrow = wind_arrow or ""
        return f"{arrow} {direction} {speed} mph"
    
    @staticmethod
    def fmt_moon_phase(phase_value: Any) -> str:
        """Format moon phase as descriptive text."""
        if phase_value is None:
            return "N/A"
        phase = float(phase_value)
        if phase < 0.125 or phase >= 0.875:
            return "New Moon"
        if phase < 0.25:
            return "Waxing Crescent"
        if phase < 0.375:
            return "First Quarter"
        if phase < 0.5:
            return "Waxing Gibbous"
        if phase < 0.625:
            return "Full Moon"
        if phase < 0.75:
            return "Waning Gibbous"
        if phase < 0.875:
            return "Last Quarter"
        return "Waning Crescent"
    
    @staticmethod
    def get_condition_emoji(condition: Any) -> str:
        """Map weather condition to emoji."""
        if not condition:
            return ""
        condition_lower = str(condition).lower()
        emoji_map = {
            "clear": "☀️",
            "sunny": "☀️",
            "clouds": "☁️",
            "cloudy": "☁️",
            "partly cloudy": "⛅",
            "rain": "🌧️",
            "rainy": "🌧️",
            "drizzle": "🌦️",
            "thunderstorm": "⛈️",
            "storm": "⛈️",
            "snow": "❄️",
            "snowy": "❄️",
            "mist": "🌫️",
            "fog": "🌫️",
            "haze": "🌫️",
        }
        for key, emoji in emoji_map.items():
            if key in condition_lower:
                return emoji
        return ""
    
    def fmt_tide_rows(self) -> str:
        """Format tide information rows for Today's Weather table.
        
        Returns HTML rows for high tide and low tide if available.
        """
        tide_summary = self.sensor_data.get("tide_summary", {})
        if not tide_summary:
            return ""
        
        today_highs = tide_summary.get("today_high_tides", [])
        today_lows = tide_summary.get("today_low_tides", [])
        
        rows = []
        
        # High Tide row
        if today_highs:
            max_high = max(today_highs, key=lambda t: t.get("height_ft", 0))
            time_str = max_high.get("time_local", "")
            height_ft = max_high.get("height_ft", 0)
            
            try:
                dt = datetime.fromisoformat(time_str)
                time_display = dt.strftime("%-I:%M %p")
            except (ValueError, TypeError):
                time_display = "N/A"
            
            rows.append(f"""<tr>
                <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">High Tide</td>
                <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{time_display} ({height_ft:.1f} ft)</td>
            </tr>""")
        
        # Low Tide row
        if today_lows:
            min_low = min(today_lows, key=lambda t: t.get("height_ft", 0))
            time_str = min_low.get("time_local", "")
            height_ft = min_low.get("height_ft", 0)
            
            try:
                dt = datetime.fromisoformat(time_str)
                time_display = dt.strftime("%-I:%M %p")
            except (ValueError, TypeError):
                time_display = "N/A"
            
            rows.append(f"""<tr>
                <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Low Tide</td>
                <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{time_display} ({height_ft:.1f} ft)</td>
            </tr>""")
        
        return "\n".join(rows)
