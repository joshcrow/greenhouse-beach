import glob
import html
import json
import os
import re
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import chart_generator
import email_templates
import narrator
import scorekeeper
import stats
import timelapse
import weekly_digest
from email_sender import send_email, get_recipients_from_env
from utils.logger import create_logger

# Lazy import of settings to avoid circular imports
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


ARCHIVE_ROOT = "/app/data/archive"

# Module-level flag for test mode (set via --test CLI argument)
_test_mode = False



def is_weekly_edition() -> bool:
    """Check if today is Sunday (Weekly Edition day)."""
    return datetime.now().weekday() == 6


log = create_logger("publisher")


def find_latest_image() -> Optional[str]:
    """Return the path to the most recent JPG image in the archive, or None.

    Searches recursively under /app/data/archive for files ending in .jpg/.jpeg.
    """

    pattern_jpg = os.path.join(ARCHIVE_ROOT, "**", "*.jpg")
    pattern_jpeg = os.path.join(ARCHIVE_ROOT, "**", "*.jpeg")
    candidates = glob.glob(pattern_jpg, recursive=True) + glob.glob(
        pattern_jpeg, recursive=True
    )

    if not candidates:
        log("No archived JPG images found; proceeding without hero image.")
        return None

    latest = max(candidates, key=os.path.getmtime)
    log(f"Selected latest hero image: {latest}")
    return latest


def load_image_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def check_stale_data(
    last_seen: Dict[str, str],
    key: str,
    threshold_hours: float = 2.0,
    test_mode: bool = False,
) -> bool:
    """Check if sensor data is stale (older than threshold).

    Args:
        last_seen: Dictionary mapping sensor keys to ISO timestamp strings
        key: Sensor key to check
        threshold_hours: Maximum age in hours before data is considered stale
        test_mode: If True, uses a much longer threshold for testing

    Returns:
        True if data is stale or missing, False if fresh
    """
    # In test mode, use 48 hours threshold to avoid false positives
    if test_mode:
        threshold_hours = 48.0

    if key not in last_seen:
        # If last_seen is empty or missing this key, don't mark as stale
        # (the sensor value exists, we just don't have timestamp metadata)
        # This prevents empty sensor tables when status.json lacks last_seen
        log(f"INFO: No timestamp found for sensor '{key}' - assuming fresh")
        return False

    try:
        timestamp_str = last_seen[key]
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        age = datetime.now(timestamp.tzinfo) - timestamp
        is_stale = age.total_seconds() > (threshold_hours * 3600)
        if is_stale:
            log(
                f"WARNING: Sensor '{key}' is stale (age: {age.total_seconds() / 3600:.1f}h)"
            )
        return is_stale
    except (ValueError, TypeError) as exc:
        log(f"WARNING: Failed to parse timestamp for '{key}': {exc}")
        return False


def load_latest_sensor_snapshot() -> Dict[str, Any]:
    """Load the latest sensor snapshot for email generation.

    MVP implementation:
    - First, try a Storyteller API status endpoint (STATUS_URL or default).
    - If that fails, try a local JSON file (STATUS_PATH, default /app/data/status.json).
    - If all else fails, return an empty dict so downstream code can still run.
    """

    # Attempt 1: HTTP status endpoint
    status_url = os.getenv("STATUS_URL", "http://storyteller_api:5000/status.json")
    try:
        with urlopen(status_url, timeout=5) as resp:
            payload = resp.read()
            data = json.loads(payload.decode("utf-8"))
            if isinstance(data, dict) and isinstance(data.get("sensors"), dict):
                return data
            if isinstance(data, dict):
                return {"sensors": data, "last_seen": {}}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:  # noqa: PERF203
        log(f"Failed to fetch sensor snapshot from {status_url}: {exc}")
    except Exception as exc:  # noqa: BLE001
        log(f"Unexpected error while fetching sensor snapshot from {status_url}: {exc}")

    # Attempt 2: Local JSON status file
    settings = _get_settings()
    status_path = settings.status_path if settings else os.getenv("STATUS_PATH", "/app/data/status.json")
    try:
        if os.path.exists(status_path):
            with open(status_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("sensors"), dict):
                return data
            if isinstance(data, dict):
                return {"sensors": data, "last_seen": {}}
    except (json.JSONDecodeError, OSError) as exc:
        log(f"Failed to load sensor snapshot from {status_path}: {exc}")

    # Fallback: empty dict (narrator + template will handle missing fields gracefully)
    log("WARNING: Using fallback minimal sensor_data; real snapshot unavailable.")
    return {"sensors": {}, "last_seen": {}}


def build_email(status_snapshot: Dict[str, Any]) -> Tuple[EmailMessage, Optional[str]]:
    """Construct the email message and return it along with the image path (if any).

    Args:
        status_snapshot: Full status.json structure with 'sensors' and 'last_seen' keys
    """

    # Extract sensors and timestamps
    # NOTE: status_daemon.py now normalizes keys using registry.json
    # So sensor_data already contains logical keys (interior_temp, exterior_temp, etc.)
    sensor_data = status_snapshot.get("sensors", {})
    last_seen = status_snapshot.get("last_seen", {})
    
    log(f"Loaded sensor data (pre-normalized by status_daemon): {list(sensor_data.keys())}")

    # Check staleness for logical sensor keys (normalized by registry)
    for key in ["interior_temp", "interior_humidity", "exterior_temp", "exterior_humidity", "satellite_battery"]:
        if key in sensor_data:
            if check_stale_data(last_seen, key, test_mode=_test_mode):
                sensor_data[f"{key}_stale"] = True
                sensor_data[key] = None

    # NOTE: Temperature conversion (C→F) now happens in status_daemon.py via registry

    # Round all sensor values to integers for cleaner AI narrative and display
    for key in [
        "interior_temp",
        "interior_humidity",
        "exterior_temp",
        "exterior_humidity",
    ]:
        if key in sensor_data and sensor_data[key] is not None:
            try:
                sensor_data[key] = round(float(sensor_data[key]))
            except (ValueError, TypeError):
                pass

    # For narrator: Pass None for stale values so AI doesn't write narratives based on old data
    narrator_data = dict(sensor_data)
    for key in list(narrator_data.keys()):
        if key.endswith("_stale") and narrator_data.get(key):
            # Find the base key and set it to None for narrator
            base_key = key.replace("_stale", "")
            if base_key in narrator_data:
                log(f"Suppressing stale data from narrator: {base_key}")
                narrator_data[base_key] = None

    # Satellite battery voltage is already calibrated in ESPHome (no *2 needed)
    # Just flag if critical for AI to mention
    # NOTE: Key is now normalized to "satellite_battery" by status_daemon
    for key in ["satellite_battery"]:
        if key in sensor_data and sensor_data[key] is not None:
            try:
                voltage = float(sensor_data[key])
                if voltage < 3.4:
                    sensor_data["satellite_battery_critical"] = True
            except (ValueError, TypeError):
                pass

    # Check if this is Weekly Edition (Sunday)
    weekly_mode = is_weekly_edition()
    weekly_summary = None

    # Get weekly stats if Sunday and merge into narrator_data
    if weekly_mode:
        log("Weekly Edition: Loading weekly stats for narrator")
        weekly_data = weekly_digest.load_weekly_stats()
        if weekly_data and weekly_data.get("days"):
            # Compute summary from raw weekly data
            ws = weekly_digest.compute_weekly_summary(weekly_data)
            # Add weekly stats to narrator_data - clearly labeled as greenhouse vs outdoor
            narrator_data["greenhouse_weekly_high"] = ws.get("interior_temp_max")
            narrator_data["greenhouse_weekly_low"] = ws.get("interior_temp_min")
            narrator_data["greenhouse_weekly_avg"] = ws.get("interior_temp_avg")
            narrator_data["outdoor_weekly_high"] = ws.get("exterior_temp_max")
            narrator_data["outdoor_weekly_low"] = ws.get("exterior_temp_min")
            narrator_data["outdoor_weekly_avg"] = ws.get("exterior_temp_avg")
            # Legacy keys for compatibility (but now clearly greenhouse)
            narrator_data["weekly_high"] = ws.get("interior_temp_max")
            narrator_data["weekly_low"] = ws.get("interior_temp_min")
            narrator_data["weekly_avg_temp"] = ws.get("interior_temp_avg")
            narrator_data["weekly_avg_humidity"] = ws.get("interior_humidity_avg")
            narrator_data["weekly_max_humidity"] = ws.get("interior_humidity_max")
            narrator_data["weekly_min_humidity"] = ws.get("interior_humidity_min")
            log(
                f"Added weekly stats to narrator: high={narrator_data.get('weekly_high')}, low={narrator_data.get('weekly_low')}"
            )

    # Narrative content and augmented data (includes weather)
    augmented_data = {}  # Initialize to ensure it's defined even if narrator fails
    body_html = ""
    body_plain = ""
    try:
        subject, headline, body_html, body_plain, augmented_data = (
            narrator.generate_update(narrator_data, is_weekly=weekly_mode, test_mode=_test_mode)
        )
        # Merge augmented data back (weather info) but preserve stale flags
        stale_flags = {k: v for k, v in sensor_data.items() if k.endswith("_stale")}
        sensor_data = {**augmented_data, **stale_flags}
    except Exception as exc:  # noqa: BLE001
        log(f"Narrator failed: {exc}")
        subject = "Greenhouse News"
        headline = "Greenhouse Update"
        body_html = "Error generating update."
        body_plain = "Error generating update."

    # Clean subject line - remove any HTML/markdown formatting (AI sometimes adds it)
    subject = re.sub(r"<[^>]+>", "", subject)  # Remove HTML tags
    subject = re.sub(r"\*+", "", subject)  # Remove markdown bold/italic
    subject = subject.strip()

    if weekly_mode:
        log("Weekly Edition: Including weekly summary and timelapse")
        # Don't override subject if narrator already made it weekly-themed
        if not subject.lower().startswith("weekly"):
            subject = f"Weekly Edition: {subject}"
        # Get weekly summary stats for display table
        weekly_data = weekly_digest.load_weekly_stats()
        if weekly_data.get("days"):
            weekly_summary = weekly_digest.compute_weekly_summary(weekly_data)
            log(f"Weekly summary: {weekly_summary}")

    # Hero image/timelapse
    image_bytes: Optional[bytes] = None
    image_cid: Optional[str] = None
    image_type = "jpeg"  # Default to jpeg, may change to gif for timelapse
    
    # Generate URL for 4K timelapse on website (deep link from email)
    from datetime import date
    yesterday = date.today() - timedelta(days=1)
    _timelapse_url = f"https://straightouttacolington.com/timelapse#daily_{yesterday.strftime('%Y-%m-%d')}"

    if weekly_mode:
        # Weekly Edition: Use existing weekly timelapse logic (golden hour stitch)
        log("Creating weekly timelapse GIF (golden hour stitch)...")
        image_bytes = timelapse.create_weekly_timelapse()
        if image_bytes:
            image_cid = make_msgid(domain="greenhouse")[1:-1]
            image_type = "gif"
            log(f"Weekly timelapse created: {len(image_bytes)} bytes")
        else:
            log("Weekly timelapse creation failed, falling back to static image")
    else:
        # Daily Edition: Use new daily timelapse (yesterday's daylight images)
        log(
            "Daily Edition: Creating daily timelapse from yesterday's daylight images..."
        )
        image_bytes = timelapse.create_daily_timelapse()
        if image_bytes:
            image_cid = make_msgid(domain="greenhouse")[1:-1]
            image_type = "gif"
            log(f"Daily timelapse created: {len(image_bytes)} bytes")
        else:
            log("Daily timelapse creation failed, falling back to static image")

    # Fall back to static image if no timelapse was created
    if image_bytes is None:
        image_path = find_latest_image()
        if image_path:
            try:
                image_bytes = load_image_bytes(image_path)
                image_cid = make_msgid(domain="greenhouse")[1:-1]
                image_type = "jpeg"
                log(f"Using static fallback image: {image_path}")
            except Exception as exc:  # noqa: BLE001
                log(f"Failed to load image '{image_path}': {exc}")
                image_bytes = None
                image_cid = None

    # Envelope fields from settings or environment
    settings = _get_settings()
    if settings:
        smtp_from = settings.smtp_from
        recipients = settings.smtp_recipients
    else:
        smtp_from = os.getenv("SMTP_FROM", "greenhouse@example.com")
        smtp_to = os.getenv("SMTP_TO", "you@example.com")
        recipients = [addr.strip() for addr in smtp_to.split(",") if addr.strip()]

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)  # Display all recipients in header
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    # Plain-text fallback (use body_plain which has HTML tags stripped)
    msg.set_content(body_plain)

    # Extract vitals with graceful fallbacks (support both old and new key formats)
    # Interior sensors (from HA bridge or direct MQTT)
    indoor_temp = sensor_data.get("interior_temp") or sensor_data.get("temp")
    indoor_humidity = sensor_data.get("interior_humidity") or sensor_data.get(
        "humidity"
    )

    # Outside sensors (logical keys from registry normalization)
    # Registry maps: satellite-2_* MQTT → exterior_* logical
    exterior_temp = sensor_data.get("exterior_temp")
    exterior_humidity = sensor_data.get("exterior_humidity")

    # Weather API outdoor conditions
    _outdoor_temp = sensor_data.get("outdoor_temp") or sensor_data.get("outside_temp")  # noqa: F841
    _outdoor_humidity = sensor_data.get("humidity_out") or sensor_data.get(
        "outside_humidity"
    )
    outdoor_condition = sensor_data.get("condition")

    # Extended weather details from weather_service (if available)
    high_temp = sensor_data.get("high_temp")
    low_temp = sensor_data.get("low_temp")

    # Use Daily Wind forecast if available (more representative), otherwise current
    wind_mph = sensor_data.get("daily_wind_mph")
    if wind_mph is None:
        wind_mph = sensor_data.get("wind_mph")
        wind_direction = sensor_data.get("wind_direction")
        wind_arrow = sensor_data.get("wind_arrow") or ""
    else:
        wind_direction = sensor_data.get("daily_wind_direction")
        wind_arrow = sensor_data.get("daily_wind_arrow") or ""

    moon_phase = sensor_data.get("moon_phase")
    moon_icon = sensor_data.get("moon_icon") or ""

    sunrise = sensor_data.get("sunrise")
    sunset = sensor_data.get("sunset")

    # Battery for outdoor sensor (normalized from satellite-2)
    sat_battery_raw = sensor_data.get("satellite_battery")
    sat_battery = round(sat_battery_raw, 1) if sat_battery_raw is not None else None

    # 24-hour stats (min/max) for vitals
    # NOTE: status_daemon.py now normalizes keys, so stats use logical keys
    stats_24h = stats.get_24h_stats(datetime.utcnow())

    # Extract 24h stats for display (now using normalized keys)
    indoor_temp_min = stats_24h.get("interior_temp_min")
    indoor_temp_max = stats_24h.get("interior_temp_max")
    indoor_humidity_min = stats_24h.get("interior_humidity_min")
    indoor_humidity_max = stats_24h.get("interior_humidity_max")

    # Outdoor temps (normalized from satellite-2)
    exterior_temp_min = stats_24h.get("exterior_temp_min")
    exterior_temp_max = stats_24h.get("exterior_temp_max")
    # Round to integers for display
    exterior_temp_min = round(exterior_temp_min) if exterior_temp_min is not None else None
    exterior_temp_max = round(exterior_temp_max) if exterior_temp_max is not None else None
    exterior_humidity_min = stats_24h.get("exterior_humidity_min")
    exterior_humidity_max = stats_24h.get("exterior_humidity_max")

    def fmt(value, stale_flag=None):
        """Format value for display as integer, returning N/A for None.

        Args:
            value: The sensor value to format
            stale_flag: Optional key to check for staleness in sensor_data
        """
        if value is None:
            return "N/A"
        try:
            formatted = str(round(float(value)))
            # Add (STALE) label if data is old
            if stale_flag and sensor_data.get(stale_flag):
                formatted += " <span style='color:#ca8a04;'>(STALE)</span>"
            return formatted
        except (ValueError, TypeError):
            return str(value)

    def fmt_battery(voltage, stale_flag=None):
        """Format battery voltage with color coding based on level.

        Battery levels (LiPo):
        - 4.2V = Full (100%)
        - 3.7V = Nominal (50%)
        - 3.4V = Low (20%) - yellow warning
        - 3.0V = Critical (5%) - red alert
        - <3.0V = Dead - red, needs immediate charge
        - Stale data = OFFLINE - gray
        """
        # Check if battery data is stale
        if stale_flag and sensor_data.get(stale_flag):
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

    def fmt_temp_high_low(high_val, low_val):
        """Format high/low temps with red/blue color styling."""
        if high_val is None and low_val is None:
            return "N/A"
        high_str = (
            f'<span style="color:#dc2626;" class="dark-text-high">{fmt(high_val)}°</span>'
            if high_val is not None
            else "N/A"
        )
        low_str = (
            f'<span style="color:#2563eb;" class="dark-text-low">{fmt(low_val)}°</span>'
            if low_val is not None
            else "N/A"
        )
        return f"{high_str} / {low_str}"

    def get_condition_emoji(condition):
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

    def fmt_moon_phase(phase_value):
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

    def fmt_wind():
        """Format wind display, handling calm conditions."""
        if wind_mph is None:
            return "N/A"
        speed = round(float(wind_mph))
        if speed < 1:
            return "Calm"
        direction = wind_direction or "N/A"
        arrow = wind_arrow or ""
        return f"{arrow} {direction} {speed} mph"

    def fmt_tide_rows():
        """Format tide information rows for Today's Weather table.

        Returns HTML rows for high tide and low tide if available.
        """
        tide_summary = sensor_data.get("tide_summary", {})
        if not tide_summary:
            return ""

        today_highs = tide_summary.get("today_high_tides", [])
        today_lows = tide_summary.get("today_low_tides", [])

        rows = []

        # High Tide row
        if today_highs:
            # Find the highest tide of the day
            max_high = max(today_highs, key=lambda t: t.get("height_ft", 0))
            time_str = max_high.get("time_local", "")
            height_ft = max_high.get("height_ft", 0)

            # Format time (extract HH:MM AM/PM from ISO timestamp)
            try:
                dt = datetime.fromisoformat(time_str)
                time_display = dt.strftime("%-I:%M %p")
            except (ValueError, TypeError):
                time_display = "N/A"

            rows.append(f"""<tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #6b9b5a; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">High Tide</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #6b9b5a; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{time_display} ({height_ft:.1f} ft)</td>
                                    </tr>""")

        # Low Tide row
        if today_lows:
            # Find the lowest tide of the day
            min_low = min(today_lows, key=lambda t: t.get("height_ft", 0))
            time_str = min_low.get("time_local", "")
            height_ft = min_low.get("height_ft", 0)

            # Format time
            try:
                dt = datetime.fromisoformat(time_str)
                time_display = dt.strftime("%-I:%M %p")
            except (ValueError, TypeError):
                time_display = "N/A"

            rows.append(f"""<tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #6b9b5a; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Low Tide</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #6b9b5a; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{time_display} ({height_ft:.1f} ft)</td>
                                    </tr>""")

        return "\n".join(rows)

    def _get_tide_compact(sensor_data):
        """Get compact tide display (single line)."""
        tide_data = sensor_data.get("tide_summary", {})
        if not tide_data:
            return ""
        today_highs = tide_data.get("today_high_tides", [])
        if today_highs:
            next_high = today_highs[0]
            time_str = next_high.get("time_local", "")
            try:
                dt = datetime.fromisoformat(time_str)
                time_display = dt.strftime("%-I:%M %p")
            except (ValueError, TypeError):
                time_display = time_str[-5:] if time_str else ""
            return f"🌊 High {time_display}"
        return ""

    def _get_tide_display(sensor_data):
        """Get compact tide display for details card."""
        tide_data = sensor_data.get("tide_summary", {})
        if not tide_data:
            return ""
        
        today_highs = tide_data.get("today_high_tides", [])
        today_lows = tide_data.get("today_low_tides", [])
        
        if not today_highs and not today_lows:
            return ""
        
        # Format high tide
        high_str = ""
        if today_highs:
            h = today_highs[0]
            try:
                dt = datetime.fromisoformat(h.get("time_local", ""))
                high_str = f"🌊 High {dt.strftime('%-I:%M %p')}"
            except (ValueError, TypeError):
                high_str = f"🌊 High {h.get('time_local', '')[-5:]}"
        
        # Format low tide
        low_str = ""
        if today_lows:
            l = today_lows[0]
            try:
                dt = datetime.fromisoformat(l.get("time_local", ""))
                low_str = f"Low {dt.strftime('%-I:%M %p')}"
            except (ValueError, TypeError):
                low_str = f"Low {l.get('time_local', '')[-5:]}"
        
        # Return compact string for details card
        if high_str and low_str:
            return f"{high_str} · {low_str}"
        return high_str or low_str

    def fmt_time(value):
        if value is None:
            return "N/A"
        return str(value)

    def fmt_temp_range():
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

    # Date subheadline
    date_subheadline = datetime.now().strftime("%A, %B %d, %Y")

    # Allow only safe HTML tags (<b>, <i>, <br>) in body HTML, escape everything else
    # First escape all HTML, then restore safe tags
    body_html_escaped = html.escape(body_html)
    body_html_escaped = body_html_escaped.replace("&lt;b&gt;", "<b>").replace(
        "&lt;/b&gt;", "</b>"
    )
    body_html_escaped = body_html_escaped.replace("&lt;i&gt;", "<i>").replace(
        "&lt;/i&gt;", "</i>"
    )

    # Convert paragraph breaks (double newlines) to HTML with spacing for readability
    body_html_escaped = body_html_escaped.replace("\n\n", "<br><br>")

    # Build 24-hour vitals section only if we have at least one metric
    has_24h_stats = any(
        m is not None
        for m in (
            indoor_temp_min,
            indoor_temp_max,
            indoor_humidity_min,
            indoor_humidity_max,
            exterior_temp_min,
            exterior_temp_max,
            exterior_humidity_min,
            exterior_humidity_max,
        )
    )

    # Generate temperature chart (168h for weekly, 24h for daily)
    temp_chart_bytes: Optional[bytes] = None
    temp_chart_cid: Optional[str] = None
    chart_hours = 168 if weekly_mode else 24
    try:
        temp_chart_bytes = chart_generator.generate_temperature_chart(hours=chart_hours)
        if temp_chart_bytes:
            temp_chart_cid = make_msgid(domain="greenhouse")[1:-1]
            log(f"Generated {chart_hours}h temperature chart: {len(temp_chart_bytes)} bytes")
    except Exception as exc:
        log(f"Failed to generate temperature chart: {exc}")

    # Get tide display for template
    tide_display = _get_tide_display(sensor_data)

    # =========================================================================
    # RENDER EMAIL VIA JINJA2 TEMPLATES
    # =========================================================================
    
    # Build alerts list for template
    alerts = []
    if low_temp is not None and low_temp < 35:
        alerts.append({"icon": "❄️", "title": "Frost Risk", "detail": f"Low of {low_temp}°F tonight"})
    if sat_battery is not None and sat_battery < 3.4:
        alerts.append({"icon": "🔋", "title": "Battery Low", "detail": "Outdoor sensor needs charging"})
    if wind_mph is not None and wind_mph > 25:
        alerts.append({"icon": "💨", "title": "High Wind", "detail": f"Gusts up to {wind_mph} mph"})
    
    # Get riddle data from sensor_data (set by narrator)
    _riddle_text = sensor_data.get("_riddle_text", "")
    _yesterday_answer = sensor_data.get("_riddle_yesterday_answer")
    
    # Riddle game integration
    _riddle_date = None
    _leaderboard = []
    _yesterdays_winners = []
    cfg = _get_settings()
    # Get bot email with fallback to env var (settings may fail in container)
    _bot_email = (cfg.smtp_user if cfg and cfg.smtp_user else None) or os.getenv("SMTP_USER", "")
    
    try:
        # Load riddle state for the date (used in mailto link)
        riddle_state = narrator._load_riddle_state()
        _riddle_date = riddle_state.get("date")
        
        # Load game data
        _leaderboard = scorekeeper.get_leaderboard(top_n=5)
        _yesterdays_winners_data = scorekeeper.get_yesterdays_winners()
        _yesterdays_winners = [w["display_name"] for w in _yesterdays_winners_data]
        
        if _leaderboard:
            log(f"Riddle leaderboard: {len(_leaderboard)} players")
        if _yesterdays_winners:
            log(f"Yesterday's winners: {_yesterdays_winners}")
    except Exception as exc:
        log(f"Error loading riddle game data: {exc}")
    
    # Load broadcast message (if any) and clear after use
    _broadcast = None
    broadcast_path = "/app/data/broadcast.json"
    try:
        if os.path.exists(broadcast_path):
            with open(broadcast_path, "r", encoding="utf-8") as f:
                _broadcast = json.load(f)
            if _broadcast and _broadcast.get("title") and _broadcast.get("message"):
                log(f"Loaded broadcast: {_broadcast.get('title')}")
                # Clear the broadcast file after loading (one-time use)
                os.remove(broadcast_path)
                log("Cleared broadcast.json after loading")
    except Exception as exc:
        log(f"Error loading broadcast: {exc}")
    
    # Build 24h stats dict for template (round all values for display)
    _stats_24h = None
    if has_24h_stats:
        _stats_24h = {
            "interior_temp_max": round(indoor_temp_max) if indoor_temp_max is not None else None,
            "interior_temp_min": round(indoor_temp_min) if indoor_temp_min is not None else None,
            "interior_humidity_max": round(indoor_humidity_max) if indoor_humidity_max is not None else None,
            "interior_humidity_min": round(indoor_humidity_min) if indoor_humidity_min is not None else None,
            "exterior_temp_max": round(exterior_temp_max) if exterior_temp_max is not None else None,
            "exterior_temp_min": round(exterior_temp_min) if exterior_temp_min is not None else None,
            "exterior_humidity_max": round(exterior_humidity_max) if exterior_humidity_max is not None else None,
            "exterior_humidity_min": round(exterior_humidity_min) if exterior_humidity_min is not None else None,
        }
    
    html_body = email_templates.render_daily_email(
        subject=subject,
        headline=headline,
        body_html=body_html_escaped,
        date_display=date_subheadline,
        interior_temp=round(indoor_temp) if indoor_temp is not None else None,
        interior_humidity=round(indoor_humidity) if indoor_humidity is not None else None,
        interior_stale=sensor_data.get("interior_temp_stale", False),
        exterior_temp=round(exterior_temp) if exterior_temp is not None else None,
        exterior_humidity=round(exterior_humidity) if exterior_humidity is not None else None,
        exterior_stale=sensor_data.get("exterior_temp_stale", False),
        condition=fmt(outdoor_condition),
        condition_emoji=get_condition_emoji(outdoor_condition),
        high_temp=high_temp,
        low_temp=low_temp,
        wind_display=fmt_wind(),
        sunrise=fmt_time(sunrise),
        sunset=fmt_time(sunset),
        moon_icon=moon_icon,
        moon_phase=fmt_moon_phase(moon_phase),
        tide_display=tide_display,
        image_cid=image_cid,
        timelapse_url=_timelapse_url,
        chart_cid=temp_chart_cid,
        stats_24h=_stats_24h,
        riddle_text=_riddle_text,
        yesterday_answer=_yesterday_answer,
        riddle_date=_riddle_date,
        bot_email=_bot_email,
        yesterdays_winners=_yesterdays_winners,
        leaderboard=_leaderboard,
        alerts=alerts if alerts else None,
        broadcast=_broadcast,
        weekly_mode=weekly_mode,
        weekly_stats=weekly_summary,
        test_mode=_test_mode,
        debug_info={
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "battery": round(sat_battery, 2) if sat_battery else "N/A",
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        } if _test_mode else None,
    )
    log("Rendered email via Jinja2 templates")

    msg.add_alternative(html_body, subtype="html")

    # Attach image/timelapse as inline related part if available
    if image_bytes and image_cid:
        try:
            # The HTML part is the last part after set_content + add_alternative
            html_part = msg.get_payload()[-1]
            filename = "timelapse.gif" if image_type == "gif" else "greenhouse.jpg"
            html_part.add_related(
                image_bytes,
                maintype="image",
                subtype=image_type,
                cid=f"<{image_cid}>",
                filename=filename,
            )
            log(f"Attached {image_type} image: {len(image_bytes)} bytes")
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to attach inline image: {exc}")

    # Attach temperature chart as inline related part if available
    if temp_chart_bytes and temp_chart_cid:
        try:
            html_part = msg.get_payload()[-1]
            html_part.add_related(
                temp_chart_bytes,
                maintype="image",
                subtype="png",
                cid=f"<{temp_chart_cid}>",
                filename="temperature_chart.png",
            )
            log(f"Attached temperature chart: {len(temp_chart_bytes)} bytes")
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to attach temperature chart: {exc}")

    return msg, weekly_mode


def run_once() -> None:
    """Run a one-off generation and delivery using latest sensor data."""

    status_snapshot = load_latest_sensor_snapshot()
    log(f"Preparing email with status snapshot: {status_snapshot.get('sensors', {})}")
    msg, weekly_mode = build_email(status_snapshot)

    # Get recipients from environment
    recipients = get_recipients_from_env()

    if weekly_mode:
        log("Sending Weekly Edition with timelapse...")
    else:
        log("Sending daily email...")

    send_email(msg, recipients)
    
    # Post-send: Reset riddle game daily log for new day
    try:
        scorekeeper.archive_daily_log()
        scorekeeper.reset_daily_log(datetime.now().date().isoformat())
        log("Riddle game: archived yesterday's log, reset for today")
    except Exception as exc:
        log(f"Warning: riddle game cleanup failed (non-fatal): {exc}")


if __name__ == "__main__":
    import sys

    # Allow --weekly flag to force weekly edition mode for testing
    _force_weekly_mode = "--weekly" in sys.argv

    # Allow --test flag to send only to primary recipient (joshcrow1193@gmail.com)
    _test_mode = "--test" in sys.argv

    if _force_weekly_mode:
        # Override the module-level function properly
        _original_is_weekly = is_weekly_edition

        def is_weekly_edition() -> bool:
            return True

        globals()["is_weekly_edition"] = is_weekly_edition
        log("TESTING: Forcing Weekly Edition mode")

    if _test_mode:
        # Override SMTP_TO to only send to primary recipient
        os.environ["SMTP_TO"] = "joshcrow1193@gmail.com"
        log("TEST MODE: Sending only to joshcrow1193@gmail.com")

    run_once()
