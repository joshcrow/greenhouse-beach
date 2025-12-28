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

# Configuration
DEVICE_OFFLINE_THRESHOLD_MINUTES = int(
    os.getenv("DEVICE_OFFLINE_THRESHOLD_MINUTES", "10")
)
MONITOR_STATE_PATH = os.getenv(
    "MONITOR_STATE_PATH", "/app/data/device_monitor_state.json"
)
STATUS_PATH = os.getenv("STATUS_PATH", "/app/data/status.json")

# Email configuration (reuse from publisher)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "Greenhouse Monitor <greenhouse@example.com>")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", os.getenv("SMTP_TO", ""))

# Device definitions: device_id -> list of sensor key prefixes
MONITORED_DEVICES = {
    "greenhouse-pi": ["interior_", "exterior_"],
    "satellite-2": ["satellite-2_"],
}


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [monitor] {message}", flush=True)


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
        os.makedirs(os.path.dirname(MONITOR_STATE_PATH) or ".", exist_ok=True)
        tmp_path = MONITOR_STATE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, MONITOR_STATE_PATH)
    except Exception as exc:
        log(f"Error saving monitor state: {exc}")


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
