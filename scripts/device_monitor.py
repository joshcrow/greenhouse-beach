"""Device monitoring with email notifications for online/offline state changes.

Monitors greenhouse devices and sends email alerts when they go online or offline.
"""

import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Dict, Optional, Any

from utils.logger import create_logger
from utils.io import atomic_write_json, atomic_read_json

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

# Load config from app.config.settings with env var fallback
_cfg = _get_settings()

# Configuration
DEVICE_OFFLINE_THRESHOLD_MINUTES = int(
    os.getenv("DEVICE_OFFLINE_THRESHOLD_MINUTES", "10")
)
MONITOR_STATE_PATH = os.getenv(
    "MONITOR_STATE_PATH", "/app/data/device_monitor_state.json"
)
UPTIME_LOG_PATH = os.getenv(
    "UPTIME_LOG_PATH", "/app/data/uptime_log.json"
)
STATUS_PATH = _cfg.status_path if _cfg else os.getenv("STATUS_PATH", "/app/data/status.json")

# Email configuration from app.config with env var fallback
SMTP_HOST = _cfg.smtp_server_host if _cfg else (os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST", "smtp.gmail.com"))
SMTP_PORT = _cfg.smtp_port if _cfg else int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = _cfg.smtp_user if _cfg else (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME", ""))
SMTP_PASS = _cfg.smtp_password if _cfg else (os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS", ""))
SMTP_FROM = _cfg.smtp_from if _cfg else os.getenv("SMTP_FROM", "Greenhouse Monitor <greenhouse@example.com>")
# Alert email defaults to first recipient in SMTP_TO list
ALERT_EMAIL = _cfg.alert_recipient if _cfg else (os.getenv("ALERT_EMAIL") or (os.getenv("SMTP_TO", "").split(",")[0].strip()))

# Device definitions: device_id -> list of sensor key prefixes
MONITORED_DEVICES = {
    "greenhouse-pi": ["interior_", "exterior_"],
    "satellite-2": ["satellite-2_"],
}


log = create_logger("monitor")


def _load_monitor_state() -> Dict[str, Any]:
    """Load the previous device state from disk."""
    try:
        if os.path.exists(MONITOR_STATE_PATH):
            with open(MONITOR_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        log(f"Error loading monitor state: {exc}")
    return {"devices": {}}


def _save_monitor_state(state: Dict[str, Any]) -> None:
    """Save the current device state to disk."""
    try:
        atomic_write_json(MONITOR_STATE_PATH, state)
    except Exception as exc:
        log(f"Error saving monitor state: {exc}")


def _load_uptime_log() -> Dict[str, Any]:
    """Load the uptime event log from disk."""
    try:
        if os.path.exists(UPTIME_LOG_PATH):
            with open(UPTIME_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        log(f"Error loading uptime log: {exc}")
    return {"events": [], "daily_stats": {}}


def _save_uptime_log(log_data: Dict[str, Any]) -> None:
    """Save the uptime event log to disk."""
    try:
        atomic_write_json(UPTIME_LOG_PATH, log_data)
    except Exception as exc:
        log(f"Error saving uptime log: {exc}")


def _log_state_change(device_id: str, is_online: bool, timestamp: datetime) -> None:
    """Log a device state change event for uptime tracking."""
    log_data = _load_uptime_log()
    events = log_data.get("events", [])
    
    event = {
        "device": device_id,
        "state": "online" if is_online else "offline",
        "timestamp": timestamp.isoformat(),
    }
    events.append(event)
    
    # Keep only last 1000 events to prevent unbounded growth
    if len(events) > 1000:
        events = events[-1000:]
    
    log_data["events"] = events
    _save_uptime_log(log_data)


def _load_status() -> Dict[str, Any]:
    """Load current sensor status."""
    try:
        if os.path.exists(STATUS_PATH):
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        log(f"Error loading status: {exc}")
    return {}


def _send_alert_email(subject: str, body: str) -> bool:
    """Send an alert email."""
    if not SMTP_USER or not SMTP_PASS or not ALERT_EMAIL:
        log("Email not configured, skipping alert")
        return False

    try:
        msg = EmailMessage()
        msg["From"] = SMTP_FROM
        msg["To"] = ALERT_EMAIL
        msg["Subject"] = subject
        msg.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        log(f"Sent alert email: {subject}")
        return True
    except Exception as exc:
        log(f"Failed to send alert email: {exc}")
        return False


def _get_device_last_seen(
    last_seen: Dict[str, str], prefixes: list
) -> Optional[datetime]:
    """Get the most recent timestamp for a device based on its sensor prefixes."""
    latest = None
    for key, ts_str in last_seen.items():
        if any(key.startswith(p) for p in prefixes):
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if latest is None or ts > latest:
                    latest = ts
            except (ValueError, TypeError):
                pass
    return latest


def _is_device_online(last_seen_ts: Optional[datetime], now: datetime) -> bool:
    """Check if a device is online based on its last seen timestamp."""
    if last_seen_ts is None:
        return False
    threshold = timedelta(minutes=DEVICE_OFFLINE_THRESHOLD_MINUTES)
    return (now - last_seen_ts) < threshold


def check_devices() -> Dict[str, bool]:
    """Check all monitored devices and send alerts for state changes.

    Returns dict of device_id -> is_online
    """
    status = _load_status()
    last_seen = status.get("last_seen", {})
    state = _load_monitor_state()
    device_states = state.get("devices", {})

    now = datetime.now(timezone.utc)
    current_states = {}

    for device_id, prefixes in MONITORED_DEVICES.items():
        device_last_seen = _get_device_last_seen(last_seen, prefixes)
        is_online = _is_device_online(device_last_seen, now)
        current_states[device_id] = is_online

        previous_state = device_states.get(device_id, {})
        was_online = previous_state.get("online", None)

        # Calculate how long ago the device was last seen
        if device_last_seen:
            age = now - device_last_seen
            age_str = (
                f"{age.days}d {age.seconds // 3600}h {(age.seconds % 3600) // 60}m ago"
            )
            last_seen_str = device_last_seen.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            age_str = "never"
            last_seen_str = "never"

        # Detect state changes
        if was_online is not None and was_online != is_online:
            # Log state change for uptime tracking
            _log_state_change(device_id, is_online, now)
            
            if is_online:
                # Device came online
                subject = f"🟢 {device_id} is back ONLINE"
                body = f"""Good news! {device_id} is back online.

Device: {device_id}
Status: ONLINE
Last seen: {last_seen_str}

The device is now sending sensor data again.
"""
                _send_alert_email(subject, body)
                log(f"Device {device_id} came ONLINE (last seen: {last_seen_str})")
            else:
                # Device went offline
                subject = f"🔴 {device_id} is OFFLINE"
                body = f"""Alert: {device_id} has gone offline.

Device: {device_id}
Status: OFFLINE
Last seen: {last_seen_str} ({age_str})
Threshold: {DEVICE_OFFLINE_THRESHOLD_MINUTES} minutes

No sensor data has been received from this device for over {DEVICE_OFFLINE_THRESHOLD_MINUTES} minutes.

Possible causes:
- Power loss (solar battery depleted)
- Network connectivity issue
- Device crash or hang
"""
                _send_alert_email(subject, body)
                log(f"Device {device_id} went OFFLINE (last seen: {age_str})")
        elif was_online is None:
            # First time seeing this device, just log it
            status_str = "ONLINE" if is_online else "OFFLINE"
            log(
                f"Device {device_id} initial state: {status_str} (last seen: {last_seen_str})"
            )

        # Update state
        device_states[device_id] = {
            "online": is_online,
            "last_seen": last_seen_str,
            "checked_at": now.isoformat(),
        }

    # Save updated state
    state["devices"] = device_states
    state["last_check"] = now.isoformat()
    _save_monitor_state(state)

    return current_states


def get_device_status() -> Dict[str, Dict[str, Any]]:
    """Get current status of all monitored devices without sending alerts."""
    status = _load_status()
    last_seen = status.get("last_seen", {})
    now = datetime.now(timezone.utc)

    result = {}
    for device_id, prefixes in MONITORED_DEVICES.items():
        device_last_seen = _get_device_last_seen(last_seen, prefixes)
        is_online = _is_device_online(device_last_seen, now)

        if device_last_seen:
            age = now - device_last_seen
            age_str = (
                f"{age.days}d {age.seconds // 3600}h {(age.seconds % 3600) // 60}m"
            )
        else:
            age_str = "never"

        result[device_id] = {
            "online": is_online,
            "last_seen": device_last_seen.isoformat() if device_last_seen else None,
            "age": age_str,
        }

    return result


def get_uptime_stats(hours: int = 24) -> Dict[str, Dict[str, Any]]:
    """Calculate uptime statistics for each device over the given time window.
    
    Args:
        hours: Number of hours to look back (default 24)
    
    Returns:
        Dict mapping device_id to stats including:
        - uptime_pct: Percentage of time online
        - downtime_minutes: Total minutes offline
        - outages: Number of offline events
        - longest_outage_minutes: Duration of longest outage
    """
    log_data = _load_uptime_log()
    events = log_data.get("events", [])
    
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours)
    
    stats = {}
    for device_id in MONITORED_DEVICES.keys():
        # Filter events for this device within the window
        device_events = [
            e for e in events
            if e.get("device") == device_id
            and datetime.fromisoformat(e["timestamp"]) >= window_start
        ]
        
        # Sort by timestamp
        device_events.sort(key=lambda e: e["timestamp"])
        
        # Calculate downtime
        total_downtime = timedelta(0)
        outages = 0
        longest_outage = timedelta(0)
        current_outage_start = None
        
        for event in device_events:
            ts = datetime.fromisoformat(event["timestamp"])
            if event["state"] == "offline":
                current_outage_start = ts
                outages += 1
            elif event["state"] == "online" and current_outage_start:
                outage_duration = ts - current_outage_start
                total_downtime += outage_duration
                if outage_duration > longest_outage:
                    longest_outage = outage_duration
                current_outage_start = None
        
        # If currently in an outage, count time until now
        if current_outage_start:
            outage_duration = now - current_outage_start
            total_downtime += outage_duration
            if outage_duration > longest_outage:
                longest_outage = outage_duration
        
        window_duration = timedelta(hours=hours)
        uptime_duration = window_duration - total_downtime
        uptime_pct = (uptime_duration / window_duration) * 100 if window_duration.total_seconds() > 0 else 100
        
        stats[device_id] = {
            "uptime_pct": round(uptime_pct, 1),
            "downtime_minutes": round(total_downtime.total_seconds() / 60, 1),
            "outages": outages,
            "longest_outage_minutes": round(longest_outage.total_seconds() / 60, 1),
        }
    
    return stats


if __name__ == "__main__":
    # When run directly, check devices and print status
    print("Checking device status...")
    states = check_devices()
    print("\nDevice Status:")
    for device_id, is_online in states.items():
        status = "🟢 ONLINE" if is_online else "🔴 OFFLINE"
        print(f"  {device_id}: {status}")

    print("\nDetailed Status:")
    details = get_device_status()
    for device_id, info in details.items():
        print(f"  {device_id}:")
        print(f"    Online: {info['online']}")
        print(f"    Last seen: {info['last_seen']}")
        print(f"    Age: {info['age']}")
    
    print("\n24h Uptime Stats:")
    uptime = get_uptime_stats(24)
    for device_id, stats in uptime.items():
        print(f"  {device_id}:")
        print(f"    Uptime: {stats['uptime_pct']}%")
        print(f"    Downtime: {stats['downtime_minutes']} minutes")
        print(f"    Outages: {stats['outages']}")
        print(f"    Longest outage: {stats['longest_outage_minutes']} minutes")
