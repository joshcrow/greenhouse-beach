import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import paho.mqtt.client as mqtt


BROKER_HOST = os.getenv("MQTT_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
# Subscribe to all sensor state topics under greenhouse/*
TOPIC_FILTER = "greenhouse/+/sensor/+/state"

STATUS_PATH = os.getenv("STATUS_PATH", "/app/data/status.json")
STATS_24H_PATH = os.getenv("STATS_24H_PATH", "/app/data/stats_24h.json")
# Persist history cache to mounted volume (survives container restarts)
HISTORY_CACHE_PATH = os.getenv("HISTORY_CACHE_PATH", "/app/data/history_cache.json")
# Long-term sensor logs directory (monthly JSONL files for analysis)
SENSOR_LOG_DIR = os.getenv("SENSOR_LOG_DIR", "/app/data/sensor_log")

# Minimum interval between disk writes (seconds)
WRITE_INTERVAL_SECONDS = int(os.getenv("STATUS_WRITE_INTERVAL", "60"))

CACHE_WRITE_INTERVAL_SECONDS = int(os.getenv("HISTORY_WRITE_INTERVAL", "300"))

# Long-term log write interval (batch writes to reduce SD card wear)
SENSOR_LOG_INTERVAL_SECONDS = int(os.getenv("SENSOR_LOG_INTERVAL", "300"))  # 5 minutes

SPIKE_WINDOW_SECONDS = int(os.getenv("SENSOR_SPIKE_WINDOW_SECONDS", "600"))
TEMP_SPIKE_F = float(os.getenv("TEMP_SPIKE_F", "20"))
HUMIDITY_SPIKE_PCT = float(os.getenv("HUMIDITY_SPIKE_PCT", "30"))

TEMP_MIN_F = float(os.getenv("TEMP_MIN_F", "-10"))
TEMP_MAX_F = float(os.getenv("TEMP_MAX_F", "130"))
HUMIDITY_MIN_PCT = float(os.getenv("HUMIDITY_MIN_PCT", "0"))
HUMIDITY_MAX_PCT = float(os.getenv("HUMIDITY_MAX_PCT", "100"))

MAX_SAMPLES_PER_KEY = int(os.getenv("MAX_SAMPLES_PER_KEY", "3000"))

# Maximum buffer size for sensor log (prevent OOM if writes fail)
MAX_SENSOR_LOG_BUFFER = int(os.getenv("MAX_SENSOR_LOG_BUFFER", "1000"))


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [status] {message}", flush=True)


# In-memory latest values and history
latest_values: Dict[str, Any] = {}
history: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
last_write: datetime = datetime.min
last_cache_write: datetime = datetime.min
last_sensor_log_write: datetime = datetime.min
last_seen: Dict[str, datetime] = {}
last_numeric_value: Dict[str, float] = {}

# Buffer for long-term sensor log (batched writes to reduce SD card wear)
sensor_log_buffer: List[Dict[str, Any]] = []


def _load_history_cache() -> None:
    """Load history from disk cache on startup to survive restarts."""
    global history, latest_values
    
    if not os.path.exists(HISTORY_CACHE_PATH):
        return
    
    try:
        with open(HISTORY_CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        
        # Restore latest values
        if "latest_values" in cache:
            latest_values.update(cache["latest_values"])

        if "last_seen" in cache and isinstance(cache["last_seen"], dict):
            for key, ts_str in cache["last_seen"].items():
                try:
                    ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).replace(tzinfo=None)
                    last_seen[key] = ts
                except Exception:
                    continue
        
        # Restore history (convert ISO strings back to datetime)
        if "history" in cache:
            now = datetime.utcnow()
            window_start = now - timedelta(hours=24)
            for key, samples in cache["history"].items():
                for ts_str, val in samples:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        # Only restore samples within last 24h
                        if ts >= window_start:
                            history[key].append((ts, float(val)))
                    except (ValueError, TypeError):
                        continue
        
        log(f"Restored history cache: {len(latest_values)} values, {sum(len(v) for v in history.values())} samples")
    except Exception as exc:  # noqa: BLE001
        log(f"Failed to load history cache: {exc}")


def _save_history_cache() -> None:
    """Persist history to disk for crash recovery."""
    try:
        # Convert datetime objects to ISO strings for JSON serialization
        history_serializable = {}
        for key, samples in history.items():
            history_serializable[key] = [
                (ts.isoformat() + "Z", val) for ts, val in samples
            ]
        
        cache = {
            "latest_values": latest_values,
            "last_seen": {k: (v.isoformat() + "Z") for k, v in last_seen.items()},
            "history": history_serializable,
            "saved_at": datetime.utcnow().isoformat() + "Z",
        }
        
        os.makedirs(os.path.dirname(HISTORY_CACHE_PATH), exist_ok=True)
        tmp_path = HISTORY_CACHE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
            f.flush()
            os.fsync(f.fileno())  # M3: Ensure data is on disk before rename
        os.replace(tmp_path, HISTORY_CACHE_PATH)
    except OSError as exc:
        log(f"Failed to save history cache: {exc}")


def _write_sensor_log() -> None:
    """Write buffered sensor readings to monthly JSONL file for long-term analysis.
    
    File format: /app/data/sensor_log/YYYY-MM.jsonl
    Each line is a JSON object: {"ts": "ISO8601", "sensors": {...}}
    """
    global sensor_log_buffer
    
    if not sensor_log_buffer:
        return
    
    try:
        os.makedirs(SENSOR_LOG_DIR, exist_ok=True)
        
        # Monthly file naming: 2025-12.jsonl
        now = datetime.utcnow()
        filename = now.strftime("%Y-%m") + ".jsonl"
        filepath = os.path.join(SENSOR_LOG_DIR, filename)
        
        # Append buffered entries to the log file
        with open(filepath, "a", encoding="utf-8") as f:
            for entry in sensor_log_buffer:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        
        log(f"Appended {len(sensor_log_buffer)} entries to sensor log {filepath}")
        sensor_log_buffer.clear()
    except Exception as exc:  # noqa: BLE001
        log(f"Failed to write sensor log: {exc}")


def _buffer_sensor_reading(now: datetime) -> None:
    """Add current sensor state to the log buffer.
    
    Caps buffer size to prevent OOM if writes fail repeatedly.
    """
    if not latest_values:
        return
    
    # Evict oldest entries if buffer is full (H2: prevent unbounded growth)
    while len(sensor_log_buffer) >= MAX_SENSOR_LOG_BUFFER:
        sensor_log_buffer.pop(0)
        log("WARNING: Sensor log buffer full, evicting oldest entry")
    
    entry = {
        "ts": now.isoformat() + "Z",
        "sensors": dict(latest_values),
    }
    sensor_log_buffer.append(entry)


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
    Returns '{device_id}_{key}' for uniqueness across zones.
    """

    parts = topic.split("/")
    if len(parts) >= 5 and parts[-1] == "state":
        device_id = parts[1]  # e.g., 'interior', 'exterior', 'satellite-2'
        sensor_key = parts[-2]  # e.g., 'temp', 'humidity'
        return f"{device_id}_{sensor_key}"
    return None


def _parts_from_topic(topic: str) -> Tuple[str, str] | None:
    parts = topic.split("/")
    if len(parts) >= 5 and parts[-1] == "state":
        return parts[1], parts[-2]
    return None


def _is_temp_sensor(sensor_key: str) -> bool:
    k = sensor_key.lower()
    return "temp" in k


def _is_humidity_sensor(sensor_key: str) -> bool:
    k = sensor_key.lower()
    return "humidity" in k


def _temp_to_f(device_id: str, value: float) -> float:
    if device_id.startswith("satellite"):
        return value * 9.0 / 5.0 + 32.0
    return value


def _validate_numeric(device_id: str, sensor_key: str, value: float) -> Tuple[bool, float]:
    if _is_temp_sensor(sensor_key):
        v_f = _temp_to_f(device_id, value)
        return (TEMP_MIN_F <= v_f <= TEMP_MAX_F), v_f
    if _is_humidity_sensor(sensor_key):
        return (HUMIDITY_MIN_PCT <= value <= HUMIDITY_MAX_PCT), value
    return True, value


def _is_spike(key: str, now: datetime, comparable_value: float, sensor_key: str) -> bool:
    prev_ts = last_seen.get(key)
    prev_val = last_numeric_value.get(key)
    if prev_ts is None or prev_val is None:
        return False
    if (now - prev_ts).total_seconds() > SPIKE_WINDOW_SECONDS:
        return False

    delta = abs(comparable_value - prev_val)
    if _is_temp_sensor(sensor_key):
        return delta > TEMP_SPIKE_F
    if _is_humidity_sensor(sensor_key):
        return delta > HUMIDITY_SPIKE_PCT
    return False


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

        # Dynamic stats key generation based on sensor key
        # Key format: {device}_{sensor} e.g., interior_temp, exterior_humidity
        # Generate stats keys: {device}_{sensor}_min, {device}_{sensor}_max
        metrics[f"{key}_min"] = min(numeric_values)
        metrics[f"{key}_max"] = max(numeric_values)

    return metrics


def _prune_key_history(now: datetime, key: str) -> None:
    window_start = now - timedelta(hours=24)
    samples = history.get(key)
    if not samples:
        return

    while samples and samples[0][0] < window_start:
        samples.pop(0)
    if len(samples) > MAX_SAMPLES_PER_KEY:
        history[key] = samples[-MAX_SAMPLES_PER_KEY:]


def _write_files_if_due(now: datetime) -> None:
    global last_write, last_cache_write, last_sensor_log_write

    if (now - last_write).total_seconds() < WRITE_INTERVAL_SECONDS:
        return
    
    # Buffer current sensor state for long-term logging
    _buffer_sensor_reading(now)

    # Write status.json
    snapshot = {
        "sensors": latest_values,
        "last_seen": {k: (v.isoformat() + "Z") for k, v in last_seen.items()},
        "updated_at": now.isoformat() + "Z",
    }
    try:
        os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
        tmp_path = STATUS_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())  # M3: Ensure data is on disk before rename
        os.replace(tmp_path, STATUS_PATH)
        log(f"Wrote latest sensor snapshot to {STATUS_PATH}: {latest_values}")
    except OSError as exc:
        log(f"Error writing status snapshot to {STATUS_PATH}: {exc}")

    # Write stats_24h.json
    metrics = _prune_and_compute_stats(now)
    stats_payload = {
        "window_start": (now - timedelta(hours=24)).isoformat() + "Z",
        "window_end": now.isoformat() + "Z",
        "metrics": metrics,
    }
    try:
        tmp_path = STATS_24H_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stats_payload, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())  # M3: Ensure data is on disk before rename
        os.replace(tmp_path, STATS_24H_PATH)
        log(f"Wrote 24h stats to {STATS_24H_PATH}: {metrics}")
    except OSError as exc:
        log(f"Error writing 24h stats to {STATS_24H_PATH}: {exc}")

    if (now - last_cache_write).total_seconds() >= CACHE_WRITE_INTERVAL_SECONDS:
        _save_history_cache()
        last_cache_write = now

    # Write long-term sensor log (batched to reduce SD card wear)
    if (now - last_sensor_log_write).total_seconds() >= SENSOR_LOG_INTERVAL_SECONDS:
        _write_sensor_log()
        last_sensor_log_write = now

    last_write = now


def on_connect(client: mqtt.Client, userdata, flags, rc, properties=None):  # type: ignore[override]
    if rc == 0:
        log(f"Connected to MQTT broker at {BROKER_HOST}:{BROKER_PORT} (rc={rc})")
        log(f"Subscribing to topic filter: {TOPIC_FILTER}")
        client.subscribe(TOPIC_FILTER)
    else:
        log(f"MQTT connection failed with rc={rc}")


def on_disconnect(client: mqtt.Client, userdata, rc, properties=None):  # type: ignore[override]
    log(f"MQTT disconnected (rc={rc})")


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):  # type: ignore[override]
    global latest_values

    try:
        key = _key_from_topic(msg.topic)
        if not key:
            log(f"Ignoring message on unexpected topic '{msg.topic}'")
            return

        parts = _parts_from_topic(msg.topic)
        if not parts:
            log(f"Ignoring message on unexpected topic '{msg.topic}'")
            return
        device_id, sensor_key = parts

        value = _parse_payload(msg.payload)
        now = datetime.utcnow()

        if isinstance(value, (int, float)):
            ok, comparable = _validate_numeric(device_id, sensor_key, float(value))
            if not ok:
                log(f"Rejected out-of-range value for '{key}': {value}")
                return
            if _is_spike(key, now, comparable, sensor_key):
                log(f"Rejected spike value for '{key}': {value}")
                return

        latest_values[key] = value
        last_seen[key] = now

        # Update history only for numeric values
        if isinstance(value, (int, float)):
            history[key].append((now, float(value)))
            last_numeric_value[key] = comparable
            _prune_key_history(now, key)

        log(f"Updated key '{key}' from topic '{msg.topic}' with value {value}")

        _write_files_if_due(now)
    except Exception as exc:  # noqa: BLE001
        log(f"Error handling status message on topic '{msg.topic}': {exc}")


def run_client_loop() -> None:
    """Run MQTT client loop with connection timeout handling (M4)."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # Set credentials if provided
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        log(f"Using MQTT authentication as user '{MQTT_USERNAME}'")

    log(f"Attempting MQTT connection to {BROKER_HOST}:{BROKER_PORT}")
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    
    # M4: Use connect with timeout via socket options
    # connect() itself doesn't have timeout, but we can set socket timeout
    import socket
    client.socket().settimeout(30.0) if client.socket() else None
    
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except (socket.timeout, OSError) as exc:
        log(f"MQTT connection timeout/error: {exc}")
        raise
    
    log("Starting MQTT network loop (loop_forever)")
    client.loop_forever()


def main() -> None:
    # Load any cached history from previous run
    _load_history_cache()
    
    while True:
        try:
            run_client_loop()
        except KeyboardInterrupt:
            log("KeyboardInterrupt received; saving cache and exiting...")
            _save_history_cache()
            _write_sensor_log()  # Flush any buffered sensor readings
            break
        except Exception as exc:  # noqa: BLE001
            log(f"Status daemon MQTT loop crashed with error: {exc}")
            _save_history_cache()  # Save before retry
            _write_sensor_log()  # Flush any buffered sensor readings
            log("Sleeping 5 seconds before retrying MQTT connection...")
            time.sleep(5)


if __name__ == "__main__":
    main()
