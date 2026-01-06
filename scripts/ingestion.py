import os
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from utils.logger import create_logger

log = create_logger("ingestion")

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

_cfg = _get_settings()
BROKER_HOST = _cfg.mqtt_host if _cfg else os.getenv("MQTT_HOST", "mosquitto")
BROKER_PORT = _cfg.mqtt_port if _cfg else int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = _cfg.mqtt_username if _cfg else os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = _cfg.mqtt_password if _cfg else os.getenv("MQTT_PASSWORD")
TOPIC_FILTER = "greenhouse/+/image"

INCOMING_DIR = "/app/data/incoming"


def ensure_incoming_dir() -> None:
    if not os.path.exists(INCOMING_DIR):
        os.makedirs(INCOMING_DIR, exist_ok=True)
        log(f"Created incoming directory at {INCOMING_DIR}")


def generate_filename(topic: str) -> str:
    """Generate a deterministic filename using UTC timestamp and topic-derived device id."""
    # topic format: greenhouse/{device_id}/image
    parts = topic.split("/")
    device_id = parts[1] if len(parts) >= 3 else "unknown"
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"img_{device_id}_{ts}.jpg"


def on_connect(client: mqtt.Client, userdata, flags, rc, properties=None):  # type: ignore[override]
    if rc == 0:
        log(f"Connected to MQTT broker at {BROKER_HOST}:{BROKER_PORT} (rc={rc})")
        log(f"Subscribing to topic filter: {TOPIC_FILTER}")
        client.subscribe(TOPIC_FILTER)
    else:
        log(f"MQTT connection failed with rc={rc}")


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):  # type: ignore[override]
    try:
        ensure_incoming_dir()
        filename = generate_filename(msg.topic)
        filepath = os.path.join(INCOMING_DIR, filename)

        # Write to a temporary file first to avoid partial reads by curator
        temp_filepath = filepath + ".tmp"
        with open(temp_filepath, "wb") as f:
            f.write(msg.payload)

        # Atomic rename to final filename
        os.rename(temp_filepath, filepath)

        log(
            f"Saved image from topic '{msg.topic}' to '{filepath}' (size={len(msg.payload)} bytes)"
        )
    except Exception as exc:  # noqa: BLE001
        log(f"Error handling message on topic '{msg.topic}': {exc}")


def run_client_loop() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    # Set credentials if provided
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        log(f"Using MQTT authentication as user '{MQTT_USERNAME}'")

    log(f"Attempting MQTT connection to {BROKER_HOST}:{BROKER_PORT}")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    log("Starting MQTT network loop (loop_forever)")
    client.loop_forever()


def main() -> None:
    ensure_incoming_dir()

    while True:
        try:
            run_client_loop()
        except KeyboardInterrupt:
            log("KeyboardInterrupt received; exiting ingestion loop.")
            break
        except Exception as exc:  # noqa: BLE001
            log(f"MQTT client crashed with error: {exc}")
            log("Sleeping 5 seconds before retrying MQTT connection...")
            time.sleep(5)


if __name__ == "__main__":
    main()
