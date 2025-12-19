# 🏠 Home Assistant Integration Setup

This guide covers setting up Home Assistant on the Greenhouse Pi to integrate with the ESP32 satellites.

---

## Overview

```
ESP32 Satellite
    │
    ├─► MQTT (greenhouse/satellite-2/sensor/*/state) ─► Storyteller (Gazette)
    │
    └─► ESPHome API (encrypted) ─► Home Assistant (Dashboard/Automation)
```

The satellite sends data via **two channels**:
1. **MQTT** → Storyteller for the Greenhouse Gazette emails
2. **ESPHome API** → Home Assistant for dashboard and automation

---

## Prerequisites

- [ ] Greenhouse Pi powered on
- [ ] Connected to same network as satellite (GREENHOUSE_IOT)
- [ ] Home Assistant running (`http://10.0.0.1:8123`)

---

## Step 1: Install ESPHome Add-on (If Not Already)

1. Open Home Assistant: `http://10.0.0.1:8123`
2. Go to **Settings** → **Add-ons** → **Add-on Store**
3. Search for **ESPHome**
4. Click **Install**
5. Enable **Start on boot** and **Watchdog**
6. Click **Start**

---

## Step 2: Add the Satellite Device

### Option A: Auto-Discovery (Easiest)

If the satellite is on the same network, Home Assistant should auto-discover it:

1. Go to **Settings** → **Devices & Services**
2. Look for **ESPHome** in discovered devices
3. Click **Configure**
4. Enter the encryption key when prompted:
   ```
   2g8GIFf0hnEVudmftFa+o7ygCQHvx0x7g1aH1fq4SOk=
   ```
5. Click **Submit**

### Option B: Manual Add

If not auto-discovered:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **ESPHome**
4. Enter the device IP (e.g., `10.0.0.20`)
5. Enter the encryption key:
   ```
   2g8GIFf0hnEVudmftFa+o7ygCQHvx0x7g1aH1fq4SOk=
   ```

---

## Step 3: Create Maintenance Mode Helper

The satellite checks for a maintenance mode toggle to stay awake for debugging.

1. Go to **Settings** → **Devices & Services** → **Helpers**
2. Click **+ Create Helper**
3. Choose **Toggle**
4. Configure:
   - **Name:** `Greenhouse Satellite 2 Maintenance`
   - **Entity ID:** `input_boolean.greenhouse_satellite_2_maintenance`
5. Click **Create**

---

## Step 4: Verify Integration

After the satellite wakes and connects:

1. Go to **Settings** → **Devices & Services** → **ESPHome**
2. Click on **Greenhouse Exterior Satellite**
3. You should see entities:
   - `sensor.satellite_2_temperature`
   - `sensor.satellite_2_humidity`
   - `sensor.satellite_2_pressure`
   - `sensor.satellite_2_battery`

---

## Step 5: Create Dashboard Card (Optional)

Add a card to your dashboard:

```yaml
type: entities
title: Greenhouse Exterior
entities:
  - entity: sensor.satellite_2_temperature
    name: Temperature
  - entity: sensor.satellite_2_humidity
    name: Humidity
  - entity: sensor.satellite_2_pressure
    name: Pressure
  - entity: sensor.satellite_2_battery
    name: Battery
  - entity: input_boolean.greenhouse_satellite_2_maintenance
    name: Maintenance Mode
```

---

## Step 6: Set Up Automation (Optional)

### Low Battery Alert

```yaml
alias: "Satellite Low Battery Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.satellite_2_battery
    below: 3.4
action:
  - service: notify.mobile_app
    data:
      message: "Satellite 2 battery is low ({{ states('sensor.satellite_2_battery') }}V)"
```

### Freeze Warning

```yaml
alias: "Greenhouse Freeze Warning"
trigger:
  - platform: numeric_state
    entity_id: sensor.satellite_2_temperature
    below: 35
action:
  - service: notify.mobile_app
    data:
      message: "Warning: Greenhouse temp is {{ states('sensor.satellite_2_temperature') }}°F"
```

---

## Troubleshooting

### Device not discovered
1. Ensure satellite is on GREENHOUSE_IOT network
2. Check satellite is awake (not in deep sleep)
3. Enable maintenance mode via MQTT to keep it awake

### "Encryption key invalid"
- Verify you're using the correct key from the YAML config
- Key must match exactly: `2g8GIFf0hnEVudmftFa+o7ygCQHvx0x7g1aH1fq4SOk=`

### Device shows unavailable
- Normal during deep sleep (15 min cycles)
- Device will show available when it wakes

### Can't enable maintenance mode
If MQTT password was changed:
1. Use Home Assistant UI toggle (if device connects via API)
2. Or re-flash satellite with correct MQTT password

---

## Reference: Satellite Credentials

| Setting | Value |
|---------|-------|
| **Device Name** | `satellite-sensor-2` |
| **API Encryption Key** | `2g8GIFf0hnEVudmftFa+o7ygCQHvx0x7g1aH1fq4SOk=` |
| **OTA Password** | `XsxdpecaLpnRgELTDxL` |
| **MQTT Broker** | `10.0.0.1` |
| **MQTT User** | `greenhouse` |

---

*Last Updated: December 2024*
