# Sensor Data Flow Architecture

> **Last Updated:** January 2026  
> **Purpose:** Definitive reference for sensor naming, mapping, and data flow

## Physical Reality vs MQTT Keys

The sensor naming is confusing due to legacy ESP32 firmware that cannot be OTA updated.

### Physical Sensors

| Physical Location | Device | HA Entity | MQTT Device ID |
|-------------------|--------|-----------|----------------|
| **INSIDE greenhouse** | HA Bridge Sensor | `sensor.greenhouse_ext_temp_persistent` | `exterior` |
| **OUTSIDE greenhouse** | Solar Satellite | N/A (ESPHome direct) | `satellite-2` |

**Yes, the "exterior" MQTT key is physically INSIDE the greenhouse.** This is legacy naming we cannot change.

---

## Data Flow Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PHYSICAL SENSORS                               │
├─────────────────────────────────────────────────────────────────────────┤
│  [Inside Greenhouse]              [Outside Greenhouse]                   │
│  HA Bridge Sensor                 Solar Satellite ESP32                  │
│  (ESPHome → HA → MQTT)            (ESPHome → MQTT direct)                │
└─────────────────────────────────────────────────────────────────────────┘
                    │                           │
                    ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           HA SENSOR BRIDGE                               │
│                     (scripts/ha_sensor_bridge.py)                        │
├─────────────────────────────────────────────────────────────────────────┤
│  sensor.greenhouse_ext_temp_persistent                                   │
│       → publishes to: greenhouse/exterior/sensor/temp/state              │
│                                                                          │
│  sensor.greenhouse_ext_humidity_persistent                               │
│       → publishes to: greenhouse/exterior/sensor/humidity/state          │
│                                                                          │
│  ⚠️  DO NOT add sensor.greenhouse_temp_persistent - causes conflict!     │
└─────────────────────────────────────────────────────────────────────────┘
                    │                           │
                    ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              MQTT BROKER                                 │
│                            (mosquitto:1883)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Topic Pattern: greenhouse/{device}/sensor/{key}/state                   │
│                                                                          │
│  greenhouse/exterior/sensor/temp/state      ← Inside greenhouse temp     │
│  greenhouse/exterior/sensor/humidity/state  ← Inside greenhouse humidity │
│  greenhouse/satellite-2/sensor/temperature/state  ← Outside temp         │
│  greenhouse/satellite-2/sensor/humidity/state     ← Outside humidity     │
└─────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           STATUS DAEMON                                  │
│                     (scripts/status_daemon.py)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  1. Parses MQTT topic → mqtt_key (e.g., "exterior_temp")                 │
│  2. Normalizes via registry.json → logical_key (e.g., "interior_temp")   │
│  3. Converts units if needed (C→F for satellite-2)                       │
│  4. Validates range (-10°F to 130°F)                                     │
│  5. Rejects spikes (>20°F change in 10 min)                              │
│  6. Stores using LOGICAL KEY only                                        │
└─────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         REGISTRY MAPPINGS                                │
│                      (configs/registry.json)                             │
├─────────────────────────────────────────────────────────────────────────┤
│  MQTT Key                  →  Logical Key (what gets stored)             │
│  ─────────────────────────────────────────────────────────               │
│  exterior_temp             →  interior_temp      ← INSIDE greenhouse     │
│  exterior_humidity         →  interior_humidity  ← INSIDE greenhouse     │
│  satellite-2_temperature   →  exterior_temp      ← OUTSIDE greenhouse    │
│  satellite-2_humidity      →  exterior_humidity  ← OUTSIDE greenhouse    │
│  satellite-2_battery       →  satellite_battery                          │
└─────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA STORAGE                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  /app/data/status.json         ← Current values (logical keys only)      │
│  /app/data/sensor_log/*.jsonl  ← Historical data (logical keys only)     │
│  /app/data/stats_weekly.json   ← Daily snapshots for weekly summary      │
│  /app/data/stats_24h.json      ← 24h rolling stats                       │
└─────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          CHART GENERATOR                                 │
│                     (scripts/chart_generator.py)                         │
├─────────────────────────────────────────────────────────────────────────┤
│  Reads from: /app/data/sensor_log/*.jsonl                                │
│                                                                          │
│  SENSOR_MAPPINGS:                                                        │
│    "Inside"  ← interior_temp, interior_humidity   (GREEN line)           │
│    "Outside" ← exterior_temp, exterior_humidity   (BLUE line)            │
│                                                                          │
│  Stats computed BEFORE resampling to preserve true H/L values            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Logical Keys (The Only Keys That Matter)

After normalization, these are the ONLY keys that exist in storage:

| Logical Key | Physical Location | Color in Charts |
|-------------|-------------------|-----------------|
| `interior_temp` | Inside greenhouse | Green |
| `interior_humidity` | Inside greenhouse | Green |
| `interior_pressure` | Inside greenhouse | - |
| `exterior_temp` | Outside greenhouse | Blue |
| `exterior_humidity` | Outside greenhouse | Blue |
| `exterior_pressure` | Outside greenhouse | - |
| `satellite_battery` | Solar satellite | - |

---

## Common Mistakes to Avoid

### ❌ DON'T: Add multiple HA sensors that map to the same logical key

```python
# BAD - causes data corruption!
SENSOR_MAP = {
    "sensor.greenhouse_temp_persistent": ("interior", "temp"),      # → interior_temp
    "sensor.greenhouse_ext_temp_persistent": ("exterior", "temp"),  # → interior_temp (via registry)
}
# Both write to interior_temp! Last one wins, causing "stuck" data.
```

### ✓ DO: Only publish sensors that have unique logical key destinations

```python
# GOOD - each sensor maps to a unique logical key
SENSOR_MAP = {
    "sensor.greenhouse_ext_temp_persistent": ("exterior", "temp"),  # → interior_temp
    # satellite-2 publishes directly via ESPHome                    # → exterior_temp
}
```

---

## Debugging Checklist

When sensor data looks wrong:

1. **Check MQTT messages:**
   ```bash
   docker compose logs storyteller | grep "Updated '"
   ```

2. **Verify no duplicate writes to same logical key:**
   ```bash
   docker compose logs storyteller | grep "interior_temp"
   # Should only see ONE source per key
   ```

3. **Check current status:**
   ```bash
   docker compose exec storyteller cat /app/data/status.json | jq .sensors
   ```

4. **Check sensor log for key consistency:**
   ```bash
   docker compose exec storyteller tail -1 /app/data/sensor_log/2026-01.jsonl | jq .sensors
   ```

---

## Historical Data Note

Data before January 2026 may contain both raw MQTT keys (e.g., `satellite-2_temperature`) AND logical keys. This was fixed in the Jan 2026 refactor. New data only contains logical keys.
