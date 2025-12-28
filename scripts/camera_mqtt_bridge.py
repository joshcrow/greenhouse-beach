#!/usr/bin/env python3
"""Camera MQTT Bridge for Greenhouse Gazette.

This script runs on the Greenhouse Pi (Node A) and:
1. Captures snapshots from the Home Assistant camera entity
2. Publishes them to MQTT for the Storyteller to ingest

Designed to run as a systemd service or cron job.

Usage:
    python3 camera_mqtt_bridge.py              # Run once (for cron)
    python3 camera_mqtt_bridge.py --daemon     # Run continuously
    python3 camera_mqtt_bridge.py --test       # Test single capture
"""

import argparse
import os
import sys
import time
from datetime import datetime
from typing import Optional

# Optional: Use libcamera directly if HA is not available
USE_LIBCAMERA_FALLBACK = True


def log(message: str) -> None:
    """Simple timestamped logger."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [camera_bridge] {message}", flush=True)


def capture_from_home_assistant(
    ha_url: str,
    ha_token: str,
    camera_entity: str,
) -> Optional[bytes]:
    """Capture a snapshot from Home Assistant camera entity.

    Args:
        ha_url: Home Assistant base URL (e.g., http://localhost:8123)
        ha_token: Long-lived access token
        camera_entity: Camera entity ID (e.g., camera.greenhouse)

    Returns:
        JPEG image bytes, or None on failure
    """
    import urllib.request
    import urllib.error

    snapshot_url = f"{ha_url}/api/camera_proxy/{camera_entity}"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }

    try:
        req = urllib.request.Request(snapshot_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            image_data = resp.read()
            if len(image_data) < 1000:
                log(f"WARNING: Image suspiciously small ({len(image_data)} bytes)")
                return None
            log(f"Captured {len(image_data)} bytes from HA camera '{camera_entity}'")
            return image_data
    except urllib.error.HTTPError as e:
        log(f"HTTP error capturing from HA: {e.code} {e.reason}")
        return None
    except urllib.error.URLError as e:
        log(f"URL error capturing from HA: {e.reason}")
        return None
    except Exception as e:
        log(f"Error capturing from HA: {e}")
        return None


def capture_from_libcamera() -> Optional[bytes]:
    """Capture a snapshot using libcamera-still (fallback method).

    Returns:
        JPEG image bytes, or None on failure
    """
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        # Capture with libcamera-still
        result = subprocess.run(
            [
                "libcamera-still",
                "-o",
                tmp_path,
                "--width",
                "1920",
                "--height",
                "1080",
                "--quality",
                "85",
                "--nopreview",
                "-t",
                "1000",  # 1 second timeout
            ],
            capture_output=True,
            timeout=15,
        )

        if result.returncode != 0:
            log(f"libcamera-still failed: {result.stderr.decode()}")
            return None

        with open(tmp_path, "rb") as f:
            image_data = f.read()

        os.unlink(tmp_path)
        log(f"Captured {len(image_data)} bytes via libcamera-still")
        return image_data

    except FileNotFoundError:
        log("libcamera-still not found - is libcamera installed?")
        return None
    except subprocess.TimeoutExpired:
        log("libcamera-still timed out")
        return None
    except Exception as e:
        log(f"Error capturing via libcamera: {e}")
        return None


def publish_to_mqtt(
    image_data: bytes,
    broker_host: str,
    broker_port: int,
    topic: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> bool:
    """Publish image bytes to MQTT.

    Args:
        image_data: JPEG image bytes
        broker_host: MQTT broker hostname/IP
        broker_port: MQTT broker port
        topic: MQTT topic to publish to
        username: Optional MQTT username
        password: Optional MQTT password

    Returns:
        True if published successfully
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log("ERROR: paho-mqtt not installed. Run: pip3 install paho-mqtt")
        return False

    try:
        client = mqtt.Client()

        if username and password:
            client.username_pw_set(username, password)

        client.connect(broker_host, broker_port, keepalive=30)
        client.loop_start()
        time.sleep(1)

        result = client.publish(topic, image_data, qos=1)
        result.wait_for_publish(timeout=10)

        if result.is_published():
            log(f"Published {len(image_data)} bytes to MQTT topic '{topic}'")
            client.disconnect()
            return True
        else:
            log(f"Failed to publish to MQTT (rc={result.rc})")
            client.disconnect()
            return False

    except Exception as e:
        log(f"MQTT publish error: {e}")
        return False


def run_once(config: dict) -> bool:
    """Capture and publish a single image.

    Args:
        config: Configuration dictionary

    Returns:
        True if successful
    """
    image_data = None

    # Try Home Assistant first
    if config.get("ha_url") and config.get("ha_token"):
        image_data = capture_from_home_assistant(
            config["ha_url"],
            config["ha_token"],
            config.get("camera_entity", "camera.greenhouse"),
        )

    # Fallback to libcamera if HA failed
    if image_data is None and USE_LIBCAMERA_FALLBACK:
        log("HA capture failed, trying libcamera fallback...")
        image_data = capture_from_libcamera()

    if image_data is None:
        log("ERROR: Failed to capture image from any source")
        return False

    # Publish to MQTT
    return publish_to_mqtt(
        image_data,
        config["mqtt_host"],
        config.get("mqtt_port", 1883),
        config.get("mqtt_topic", "greenhouse/camera/main/image"),
        config.get("mqtt_username"),
        config.get("mqtt_password"),
    )


def run_daemon(config: dict, interval_minutes: int = 30) -> None:
    """Run continuously, capturing at regular intervals.

    Args:
        config: Configuration dictionary
        interval_minutes: Minutes between captures
    """
    log(f"Starting daemon mode, capturing every {interval_minutes} minutes")

    while True:
        try:
            success = run_once(config)
            if not success:
                log("Capture cycle failed, will retry next interval")
        except Exception as e:
            log(f"Unexpected error in capture cycle: {e}")

        time.sleep(interval_minutes * 60)


def load_config() -> dict:
    """Load configuration from environment variables."""
    return {
        # Home Assistant settings
        "ha_url": os.getenv("HA_URL", "http://localhost:8123"),
        "ha_token": os.getenv("HA_TOKEN"),
        "camera_entity": os.getenv("HA_CAMERA_ENTITY", "camera.greenhouse"),
        # MQTT settings
        "mqtt_host": os.getenv("MQTT_HOST", "192.168.1.50"),  # Storyteller IP
        "mqtt_port": int(os.getenv("MQTT_PORT", "1883")),
        "mqtt_topic": os.getenv("MQTT_TOPIC", "greenhouse/camera/main/image"),
        "mqtt_username": os.getenv("MQTT_USERNAME"),
        "mqtt_password": os.getenv("MQTT_PASSWORD"),
        # Daemon settings
        "capture_interval": int(os.getenv("CAPTURE_INTERVAL_MINUTES", "60")),
        # Golden hour capture times (comma-separated HH:MM, e.g., "16:00,06:30")
        "golden_hour_times": os.getenv("GOLDEN_HOUR_TIMES", ""),
    }


# Seasonal golden hour times (1 hour before sunset for Outer Banks ~36°N)
SEASONAL_GOLDEN_HOURS = {
    1: "16:00",
    2: "16:30",
    3: "17:15",
    4: "18:45",
    5: "19:15",
    6: "19:30",
    7: "19:30",
    8: "19:00",
    9: "18:15",
    10: "17:30",
    11: "15:45",
    12: "15:45",
}


def get_golden_hour_for_month() -> str:
    """Get the golden hour time for the current month."""
    return SEASONAL_GOLDEN_HOURS.get(datetime.now().month, "16:30")


def is_golden_hour_time(config: dict) -> bool:
    """Check if current time matches any golden hour capture time."""
    now = datetime.now()
    current_time = now.strftime("%H:%M")

    # Check configured times
    gh_times = config.get("golden_hour_times", "")
    if gh_times:
        times = [t.strip() for t in gh_times.split(",")]
    else:
        # Use seasonal default
        times = [get_golden_hour_for_month()]

    for t in times:
        if current_time == t:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Camera MQTT Bridge for Greenhouse Gazette"
    )
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument(
        "--test", action="store_true", help="Test capture without publishing"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Capture interval in minutes (daemon mode)",
    )
    args = parser.parse_args()

    config = load_config()

    # Validate config
    if not config.get("ha_token") and not USE_LIBCAMERA_FALLBACK:
        log(
            "ERROR: HA_TOKEN environment variable required (or enable libcamera fallback)"
        )
        sys.exit(1)

    if args.test:
        # Test mode: just capture, don't publish
        log("Running in test mode...")
        image_data = None

        if config.get("ha_url") and config.get("ha_token"):
            image_data = capture_from_home_assistant(
                config["ha_url"],
                config["ha_token"],
                config.get("camera_entity", "camera.greenhouse"),
            )

        if image_data is None and USE_LIBCAMERA_FALLBACK:
            image_data = capture_from_libcamera()

        if image_data:
            # Save test image locally
            test_path = "/tmp/camera_bridge_test.jpg"
            with open(test_path, "wb") as f:
                f.write(image_data)
            log(f"Test image saved to {test_path} ({len(image_data)} bytes)")
            sys.exit(0)
        else:
            log("Test capture failed")
            sys.exit(1)

    if args.daemon:
        run_daemon(config, args.interval)
    else:
        success = run_once(config)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
