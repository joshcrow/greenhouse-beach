import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import paho.mqtt.client as mqtt


BROKER_HOST = os.getenv("MQTT_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
# Subscribe to all sensor state topics under greenhouse/*
TOPIC_FILTER = "greenhouse/+/sensor/+/state"

STATUS_PATH = os.getenv("STATUS_PATH", "/app/data/status.json")
STATS_24H_PATH = os.getenv("STATS_24H_PATH", "/app/data/stats_24h.json")

# Minimum interval between disk writes (seconds)
WRITE_INTERVAL_SECONDS = int(os.getenv("STATUS_WRITE_INTERVAL", "60"))


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [status] {message}", flush=True)


# In-memory latest values and history
latest_values: Dict[str, Any] = {}
history: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
last_write: datetime = datetime.min


def _parse_payload(payload: bytes) -> Any:
    text = payload.decode("utf-8").strip()
    # Try float, fall back to raw string
    try:
        return float(text)
    except ValueError:
        return text


def _key_from_topic(topic: str) -> str | None:
    """Extract logical sensor key from MQTT topic.

    Expected topic format: greenhouse/{device_id}/sensor/{key}/state
    Returns the {key} segment.
    """

    parts = topic.split("/")
    if len(parts) >= 5 and parts[-1] == "state":
        return parts[-2]
    return None


def _prune_and_compute_stats(now: datetime) -> Dict[str, Any]:
    """Prune history older than 24h and compute min/max per key.

    Returns a metrics dict suitable for stats_24h.json.
    """

    window_start = now - timedelta(hours=24)
    metrics: Dict[str, Any] = {}

    for key, samples in history.items():
        # Keep only samples within the last 24 hours
        recent = [(ts, val) for ts, val in samples if ts >= window_start]
        history[key] = recent

        numeric_values = [val for _, val in recent if isinstance(val, (int, float))]
        if not numeric_values:
            continue

        k_low = None
        k_high = None

        if key == "temp":
            k_low = "indoor_temp_min"
            k_high = "indoor_temp_max"
        elif key == "humidity":
            k_low = "indoor_humidity_min"
            k_high = "indoor_humidity_max"
        elif key == "satellite_2_temperature":
            k_low = "satellite_temp_min"
            k_high = "satellite_temp_max"
        elif key == "satellite_2_humidity":
            k_low = "satellite_humidity_min"
            k_high = "satellite_humidity_max"

        if k_low and k_high:
            metrics[k_low] = min(numeric_values)
            metrics[k_high] = max(numeric_values)

    return metrics


def _write_files_if_due(now: datetime) -> None:
    global last_write

    if (now - last_write).total_seconds() < WRITE_INTERVAL_SECONDS:
        return

    # Write status.json
    snapshot = {
        "sensors": latest_values,
        "updated_at": now.isoformat() + "Z",
    }
    try:
        os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)
        log(f"Wrote latest sensor snapshot to {STATUS_PATH}: {latest_values}")
    except Exception as exc:  # noqa: BLE001
        log(f"Error writing status snapshot to {STATUS_PATH}: {exc}")

    # Write stats_24h.json
    metrics = _prune_and_compute_stats(now)
    stats_payload = {
        "window_start": (now - timedelta(hours=24)).isoformat() + "Z",
        "window_end": now.isoformat() + "Z",
        "metrics": metrics,
    }
    try:
        with open(STATS_24H_PATH, "w", encoding="utf-8") as f:
            json.dump(stats_payload, f, indent=2, sort_keys=True)
        log(f"Wrote 24h stats to {STATS_24H_PATH}: {metrics}")
    except Exception as exc:  # noqa: BLE001
        log(f"Error writing 24h stats to {STATS_24H_PATH}: {exc}")

    last_write = now


def on_connect(client: mqtt.Client, userdata, flags, rc, properties=None):  # type: ignore[override]
    if rc == 0:
        log(f"Connected to MQTT broker at {BROKER_HOST}:{BROKER_PORT} (rc={rc})")
        log(f"Subscribing to topic filter: {TOPIC_FILTER}")
        client.subscribe(TOPIC_FILTER)
    else:
        log(f"MQTT connection failed with rc={rc}")


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):  # type: ignore[override]
    global latest_values

    try:
        key = _key_from_topic(msg.topic)
        if not key:
            log(f"Ignoring message on unexpected topic '{msg.topic}'")
            return

        value = _parse_payload(msg.payload)
        now = datetime.utcnow()

        latest_values[key] = value

        # Update history only for numeric values
        if isinstance(value, (int, float)):
            history[key].append((now, float(value)))

        log(f"Updated key '{key}' from topic '{msg.topic}' with value {value}")

        _write_files_if_due(now)
    except Exception as exc:  # noqa: BLE001
        log(f"Error handling status message on topic '{msg.topic}': {exc}")


def run_client_loop() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    log(f"Attempting MQTT connection to {BROKER_HOST}:{BROKER_PORT}")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    log("Starting MQTT network loop (loop_forever)")
    client.loop_forever()


def main() -> None:
    while True:
        try:
            run_client_loop()
        except KeyboardInterrupt:
            log("KeyboardInterrupt received; exiting status daemon loop.")
            break
        except Exception as exc:  # noqa: BLE001
            log(f"Status daemon MQTT loop crashed with error: {exc}")
            log("Sleeping 5 seconds before retrying MQTT connection...")
            time.sleep(5)


if __name__ == "__main__":
    main()
