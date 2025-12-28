import glob
import html
import json
import os
import re
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import narrator
import smtplib
import stats
import timelapse
import weekly_digest


ARCHIVE_ROOT = "/app/data/archive"

# Module-level flag for test mode (set via --test CLI argument)
_test_mode = False


def is_weekly_edition() -> bool:
    """Check if today is Sunday (Weekly Edition day)."""
    return datetime.now().weekday() == 6


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [publisher] {message}", flush=True)


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
        log(f"WARNING: No timestamp found for sensor '{key}' - marking as stale")
        return True

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
        return True


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
    status_path = os.getenv("STATUS_PATH", "/app/data/status.json")
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
    sensor_data = status_snapshot.get("sensors", {})
    last_seen = status_snapshot.get("last_seen", {})

    # SENSOR REMAPPING: Map physical reality to logical roles
    # Physical Reality:
    # - exterior_* keys = Actually INSIDE the greenhouse (main interior sensor)
    # - satellite-2_* keys = Actually OUTSIDE the greenhouse (weather/exterior)
    # - interior_* keys = BROKEN hardware, suppress from email

    remapped_data: Dict[str, Any] = {}

    # Define sensor mapping: (raw_key, logical_key)
    sensor_mapping = [
        ("exterior_temp", "interior_temp"),
        ("exterior_humidity", "interior_humidity"),
        ("satellite-2_temperature", "exterior_temp"),
        ("satellite-2_humidity", "exterior_humidity"),
    ]

    # Apply mapping with stale data checking
    for raw_key, logical_key in sensor_mapping:
        if raw_key in sensor_data:
            if not check_stale_data(last_seen, raw_key, test_mode=_test_mode):
                remapped_data[logical_key] = sensor_data[raw_key]
            else:
                remapped_data[logical_key] = None
                remapped_data[f"{logical_key}_stale"] = True

    # Satellite battery (keep for monitoring, check staleness)
    for key in ["satellite-2_battery"]:
        if key in sensor_data:
            if not check_stale_data(last_seen, key, test_mode=_test_mode):
                remapped_data[key] = sensor_data[key]
            else:
                remapped_data[key] = None
                remapped_data[f"{key}_stale"] = True

    # SUPPRESS old interior_* keys (broken hardware)
    # Do NOT copy interior_temp or interior_humidity to remapped_data

    # Copy any other sensor data that isn't being remapped
    for key, value in sensor_data.items():
        if (
            key not in remapped_data
            and not key.startswith("interior_")
            and not key.startswith("exterior_")
            and not key.startswith("satellite-2_")
        ):
            remapped_data[key] = value

    # Use remapped data for the rest of the function
    sensor_data = remapped_data
    log(f"Remapped sensor data: {sensor_data}")

    # NOTE: Satellite temperature is already in Fahrenheit from ESPHome config
    # No conversion needed - the BME280 filter in ESPHome converts C->F

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
    for key in [
        "satellite-2_battery",
        "satellite-2_satellite_2_battery",
        "satellite_2_battery",
    ]:
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
        if weekly_data:
            # Add weekly stats to narrator_data with correct keys from weekly_digest
            narrator_data["weekly_high"] = weekly_data.get("temp_max")
            narrator_data["weekly_low"] = weekly_data.get("temp_min")
            narrator_data["weekly_avg_temp"] = weekly_data.get("temp_avg")
            narrator_data["weekly_avg_humidity"] = weekly_data.get("humidity_avg")
            narrator_data["weekly_max_humidity"] = weekly_data.get("humidity_max")
            narrator_data["weekly_min_humidity"] = weekly_data.get("humidity_min")
            log(
                f"Added weekly stats to narrator: high={narrator_data.get('weekly_high')}, low={narrator_data.get('weekly_low')}"
            )

    # Narrative content and augmented data (includes weather)
    augmented_data = {}  # Initialize to ensure it's defined even if narrator fails
    body_html = ""
    body_plain = ""
    try:
        subject, headline, body_html, body_plain, augmented_data = (
            narrator.generate_update(narrator_data, is_weekly=weekly_mode)
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

    # Envelope fields from environment
    smtp_from = os.getenv("SMTP_FROM", "greenhouse@example.com")
    smtp_to = os.getenv("SMTP_TO", "you@example.com")

    msg = EmailMessage()
    msg["From"] = smtp_from
    # Handle multiple recipients separated by commas
    recipients = [addr.strip() for addr in smtp_to.split(",") if addr.strip()]
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

    # Exterior sensors (from HA bridge)
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

    # Battery for exterior/garden sensor (remapped from satellite-2)
    sat_battery_raw = sensor_data.get("satellite-2_battery")
    sat_battery = round(sat_battery_raw, 1) if sat_battery_raw is not None else None

    # 24-hour stats (min/max) for vitals
    # Keys match status_daemon.py format: {device}_{sensor}_min/max
    # NOTE: Stats are based on RAW MQTT keys (exterior_*, satellite-2_*) not remapped keys
    stats_24h = stats.get_24h_stats(datetime.utcnow())

    # Extract 24h stats for display
    indoor_temp_min = stats_24h.get("interior_temp_min")
    indoor_temp_max = stats_24h.get("interior_temp_max")
    indoor_humidity_min = stats_24h.get("interior_humidity_min")
    indoor_humidity_max = stats_24h.get("interior_humidity_max")

    exterior_temp_min = stats_24h.get("exterior_temp_min")
    exterior_temp_max = stats_24h.get("exterior_temp_max")
    exterior_humidity_min = stats_24h.get("exterior_humidity_min")
    exterior_humidity_max = stats_24h.get("exterior_humidity_max")
    exterior_temp_min = (
        round(exterior_temp_min * 9 / 5 + 32) if exterior_temp_min is not None else None
    )
    exterior_temp_max = (
        round(exterior_temp_max * 9 / 5 + 32) if exterior_temp_max is not None else None
    )
    exterior_humidity_min = stats_24h.get("satellite-2_humidity_min")
    exterior_humidity_max = stats_24h.get("satellite-2_humidity_max")

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
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">High Tide</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{time_display} ({height_ft:.1f} ft)</td>
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
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Low Tide</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{time_display} ({height_ft:.1f} ft)</td>
                                    </tr>""")

        return "\n".join(rows)

    def build_debug_footer(status_snapshot, sensor_data, augmented_data=None):
        """Build debug footer for test emails only.

        Shows data timestamp, battery voltage, and narrator model.
        Only displayed when --test flag is used.
        """
        # Check if we're in test mode
        import sys

        if "--test" not in sys.argv:
            return ""

        # Get debug info
        data_timestamp = status_snapshot.get("updated_at", "N/A")
        battery_raw = sensor_data.get("satellite-2_battery", "N/A")
        narrator_model = (
            augmented_data.get("_narrator_model", "N/A") if augmented_data else "N/A"
        )

        return f"""
    <!-- DEBUG FOOTER (Test Mode Only) -->
    <div style="margin-top: 40px; padding: 20px; text-align: center; font-family: 'Courier New', monospace; font-size: 10px; color: #9ca3af; border-top: 1px solid #e5e7eb;">
        <div>Data Timestamp: {data_timestamp}</div>
        <div>Battery Voltage: {battery_raw}V</div>
        <div>Narrator Model: {narrator_model}</div>
    </div>
"""

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

    # Build hero image section if available
    hero_section = ""
    if image_cid:
        hero_section = f"""
        <!-- CARD 0: HERO -->
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 0; border-radius: 12px; overflow: hidden;" class="dark-bg-card">
            <tr>
                <td style="padding: 0;">
                    <img src="cid:{image_cid}" alt="Greenhouse hero image" style="display:block; width:100%; height:auto; border:0;">
                </td>
            </tr>
        </table>
        """

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

    vitals_24h_section = ""
    if has_24h_stats:
        vitals_24h_section = f"""
                    <!-- CARD 2B: 24h VITALS -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 2px solid #588157; border-radius: 12px; overflow: hidden;" class="dark-border dark-bg-card">
                        <tr>
                            <td style="padding: 16px;">
                                <div class="dark-text-accent" style="font-size:13px; color:#588157; margin-bottom:12px; font-weight:600; text-transform: uppercase; letter-spacing: 0.5px;">
                                    24-hour High / Low
                                </div>
                                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size:14px; border-collapse: collapse;">
                                    <tr>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Location</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Temp (°F) High / Low</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Humidity (%) High / Low</th>
                                    </tr>
                                    {
            "".join(
                [
                    f'''<tr>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">Greenhouse</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt_temp_high_low(indoor_temp_max, indoor_temp_min)}</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(indoor_humidity_max)}% / {fmt(indoor_humidity_min)}%</td>
                                    </tr>'''
                    if any(
                        x is not None
                        for x in [
                            indoor_temp_min,
                            indoor_temp_max,
                            indoor_humidity_min,
                            indoor_humidity_max,
                        ]
                    )
                    else "",
                    f'''<tr>
                                        <td class="dark-text-primary" style="padding:12px 0; border-bottom:none; color:#1e1e1e;">Outside</td>
                                        <td class="dark-text-primary" style="padding:12px 0; border-bottom:none; color:#1e1e1e;">{fmt_temp_high_low(exterior_temp_max, exterior_temp_min)}</td>
                                        <td class="dark-text-primary" style="padding:12px 0; border-bottom:none; color:#1e1e1e;">{fmt(exterior_humidity_max)}% / {fmt(exterior_humidity_min)}%</td>
                                    </tr>'''
                    if any(
                        x is not None
                        for x in [
                            exterior_temp_min,
                            exterior_temp_max,
                            exterior_humidity_min,
                            exterior_humidity_max,
                        ]
                    )
                    else "",
                ]
            )
        }
                                </table>
                            </td>
                        </tr>
                    </table>
        """

    # Build Weekly Summary section for Sunday emails
    weekly_summary_section = ""
    if weekly_mode and weekly_summary:
        ws = weekly_summary
        weekly_summary_section = f"""
                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    <!-- CARD: WEEKLY SUMMARY -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 2px solid #588157; border-radius: 12px; overflow: hidden;" class="dark-border dark-bg-card">
                        <tr>
                            <td style="padding: 16px;">
                                <div class="dark-text-accent" style="font-size:13px; color:#588157; margin-bottom:12px; font-weight:600; text-transform: uppercase; letter-spacing: 0.5px;">
                                    📊 This Week's Summary
                                </div>
                                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size:14px; border-collapse: collapse;">
                                    <tr>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal;">Metric</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal;">Week Range</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal;">Average</th>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">Temperature</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(ws.get("temp_min"))}° – {fmt(ws.get("temp_max"))}°</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(ws.get("temp_avg"))}°</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-primary" style="padding:12px 0; color:#1e1e1e;">Humidity</td>
                                        <td class="dark-text-primary" style="padding:12px 0; color:#1e1e1e;">{fmt(ws.get("humidity_min"))}% – {fmt(ws.get("humidity_max"))}%</td>
                                        <td class="dark-text-primary" style="padding:12px 0; color:#1e1e1e;">{fmt(ws.get("humidity_avg"))}%</td>
                                    </tr>
                                </table>
                                <p class="dark-text-muted" style="color: #9ca3af; font-size: 12px; margin-top: 12px; margin-bottom: 0; text-align: center;">
                                    Based on {ws.get("days_recorded", 0)} days of data
                                </p>
                            </td>
                        </tr>
                    </table>
        """

    # HTML body with light/dark mode support
    html_body = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="light dark" />
    <meta name="supported-color-schemes" content="light dark" />
    <title>Update</title>
    <style type="text/css">
        /* RESET STYLES */
        body {{ margin: 0; padding: 0; min-width: 100%; background-color: #ffffff; font-family: Arial, sans-serif; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table {{ border-spacing: 0; border-collapse: collapse; }}
        td, th {{ padding: 0; vertical-align: top; }}
        img {{ border: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; display: block; }}
        
        /* PREVENT BLUE LINKS IN APPLE MAIL */
        a[x-apple-data-detectors] {{ color: inherit !important; text-decoration: none !important; font-size: inherit !important; font-family: inherit !important; font-weight: inherit !important; line-height: inherit !important; }}
        
        /* DARK MODE SUPPORT */
        :root {{
            color-scheme: light dark;
            supported-color-schemes: light dark;
        }}

        /* CLIENT SPECIFIC OVERRIDES */
        @media screen and (max-width: 600px) {{
            .container {{ width: 100% !important; max-width: 100% !important; }}
            .mobile-padding {{ padding-left: 16px !important; padding-right: 16px !important; }}
        }}

        @media (prefers-color-scheme: dark) {{
            /* Main Background: Neutral Dark (#171717) */
            body, .body-bg {{ background-color: #171717 !important; color: #f5f5f5 !important; }}
            
            /* Text Colors: Neutral Grays */
            .dark-text-primary {{ color: #f5f5f5 !important; }}
            .dark-text-secondary {{ color: #d4d4d4 !important; }}
            .dark-text-muted {{ color: #a3a3a3 !important; }}
            
            /* Temperature Colors */
            .dark-text-high {{ color: #f87171 !important; }}  /* Lighter red for dark mode */
            .dark-text-low {{ color: #60a5fa !important; }}   /* Lighter blue for dark mode */
            
            /* Accents: Main Green (#588157) */
            .dark-text-accent {{ color: #588157 !important; }}
            .dark-border {{ border-color: #588157 !important; }}
            
            /* Cards: Explicitly match body color in dark mode (No visual fill) */
            .dark-bg-card {{ background-color: #171717 !important; }}
            
            /* Gmail Web hack - match color scheme above */
            u + .body .body-bg {{ background-color: #171717 !important; }}
            u + .body .dark-bg-card {{ background-color: #171717 !important; }}
            u + .body .dark-text-primary {{ color: #f5f5f5 !important; }}
            u + .body .dark-text-secondary {{ color: #d4d4d4 !important; }}
            u + .body .dark-text-muted {{ color: #a3a3a3 !important; }}
            u + .body .dark-text-high {{ color: #f87171 !important; }}
            u + .body .dark-text-low {{ color: #60a5fa !important; }}
            u + .body .dark-text-accent {{ color: #588157 !important; }}
            u + .body .dark-border {{ border-color: #588157 !important; }}
        }}
    </style>
    <!--[if mso]>
    <style type="text/css">
        body, table, td, th, p, div {{ font-family: Arial, sans-serif !important; }}
        /* Fix for Outlook vertical rhythm */
        td {{ mso-line-height-rule: exactly; }}
    </style>
    <![endif]-->
</head>
<body class="body-bg" style="margin:0; padding:0; background-color:#ffffff; color:#1e1e1e;">
    
    <!-- WRAPPER -->
    <center role="article" aria-roledescription="email" lang="en" style="width:100%; background-color:#ffffff;" class="body-bg">
        
        <!--[if mso]>
        <table role="presentation" align="center" border="0" cellpadding="0" cellspacing="0" width="600">
        <tr>
        <td>
        <![endif]-->
        
        <table role="presentation" class="container" align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px; margin:0 auto;">
            <tr>
                <td style="padding: 20px;" class="mobile-padding">
                    
                    <!-- HEADER -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                        <tr>
                            <td class="dark-text-accent" style="padding-bottom: 4px; font-size:24px; font-weight: bold; color:#588157; line-height: 1.1; mso-line-height-rule: exactly;">
                                {headline}
                            </td>
                        </tr>
                        <tr>
                            <td class="dark-text-muted" style="padding-bottom: 24px; font-size:13px; color:#6b7280; mso-line-height-rule: exactly;">
                                {date_subheadline}
                            </td>
                        </tr>
                    </table>

                    <!-- CARD 1: BODY -->
                    <!-- border-spacing: 0 is critical when using separate borders -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 0; border-radius: 12px; overflow: hidden;" class="dark-bg-card">
                        <tr>
                            <td style="padding: 0;">
                                <p class="dark-text-primary" style="margin:0; line-height:1.6; color:#1e1e1e; font-size: 16px;">
                                    {body_html_escaped}
                                </p>
                            </td>
                        </tr>
                    </table>

                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    {hero_section}

                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    {vitals_24h_section}

                    {weekly_summary_section}

                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    <!-- CARD 2: SENSORS (Current + 24h High/Low) -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 2px solid #588157; border-radius: 12px; overflow: hidden;" class="dark-border dark-bg-card">
                        <tr>
                            <td style="padding: 16px;">
                                <div class="dark-text-accent" style="font-size:13px; color:#588157; margin-bottom:12px; font-weight:600; text-transform: uppercase; letter-spacing: 0.5px;">
                                    Sensors (Current)
                                </div>
                                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size:14px; border-collapse: collapse;">
                                    <tr>
                                        <!-- Note: TH tags in Apple Mail are bold by default. Explicitly setting font-weight: normal -->
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Location</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Temp</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Humidity</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Battery</th>
                                    </tr>
                                    {
        "".join(
            [
                f'''<tr>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">Interior</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(indoor_temp, 'interior_temp_stale')}°</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(indoor_humidity, 'interior_humidity_stale')}%</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">—</td>
                                    </tr>'''
                if indoor_temp is not None or indoor_humidity is not None
                else "",
                f'''<tr>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">Outside</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(exterior_temp, 'exterior_temp_stale')}°</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(exterior_humidity, 'exterior_humidity_stale')}%</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt_battery(sat_battery, 'satellite-2_battery_stale')}</td>
                                    </tr>'''
                if not (
                    sensor_data.get("exterior_temp_stale")
                    and sensor_data.get("exterior_humidity_stale")
                    and sensor_data.get("satellite-2_battery_stale")
                )
                else "",
            ]
        )
    }
                                </table>
                            </td>
                        </tr>
                    </table>

                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    <!-- CARD 3: WEATHER -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 2px solid #588157; border-radius: 12px; overflow: hidden;" class="dark-border dark-bg-card">
                        <tr>
                            <td style="padding: 16px;">
                                <div class="dark-text-accent" style="font-size:13px; color:#588157; margin-bottom:12px; font-weight:600; text-transform: uppercase; letter-spacing: 0.5px;">
                                    Today's Weather
                                </div>
                                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size:14px; border-collapse: collapse;">
                                    <tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; width: 40%; vertical-align:middle; mso-line-height-rule: exactly;">Condition</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{
        get_condition_emoji(outdoor_condition)
    } {fmt(outdoor_condition)}</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">High / Low</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{
        fmt_temp_range()
    }</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Sunrise / Sunset</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{
        fmt_time(sunrise)
    } / {fmt_time(sunset)}</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Wind</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{
        fmt_wind()
    }</td>
                                    </tr>
                                    {fmt_tide_rows()}
                                    <tr>
                                        <td class="dark-text-secondary" style="padding: 12px 0; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Moon Phase</td>
                                        <td class="dark-text-primary" style="padding: 12px 0; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">
                                            <table align="right" border="0" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
                                                <tr>
                                                    <td class="dark-text-primary" style="padding-right: 6px; color:#1e1e1e; vertical-align:middle; font-size: 14px; line-height: 1;">{
        moon_icon
    }</td>
                                                    <td class="dark-text-primary" style="color:#1e1e1e; vertical-align:middle; font-size: 14px;">{
        fmt_moon_phase(moon_phase)
    }</td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>

                </td>
            </tr>
        </table>
        
        <!--[if mso]>
        </td>
        </tr>
        </table>
        <![endif]-->
        
    </center>
    
    {build_debug_footer(status_snapshot, sensor_data, augmented_data)}
</body>
</html>
"""

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

    return msg, weekly_mode


def send_email(msg: EmailMessage, recipients: list[str] = None) -> None:
    """Send the email via SMTP over SSL using environment variables."""

    smtp_server = os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not smtp_server:
        log("ERROR: SMTP_SERVER/SMTP_HOST is not configured; cannot send email.")
        return

    log(f"Connecting to SMTP server {smtp_server}:{smtp_port} using SSL...")

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            # Send to all recipients
            server.send_message(msg, to_addrs=recipients)
        log(f"Email sent successfully to {len(recipients)} recipients.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error while sending email: {exc}")


def run_once() -> None:
    """Run a one-off generation and delivery using latest sensor data."""

    status_snapshot = load_latest_sensor_snapshot()
    log(f"Preparing email with status snapshot: {status_snapshot.get('sensors', {})}")
    msg, weekly_mode = build_email(status_snapshot)

    # Parse recipients from environment
    smtp_to = os.getenv("SMTP_TO", "you@example.com")
    recipients = [addr.strip() for addr in smtp_to.split(",") if addr.strip()]

    if weekly_mode:
        log("Sending Weekly Edition with timelapse...")
    else:
        log("Sending daily email...")

    send_email(msg, recipients)


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
