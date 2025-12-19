# 📟 ESP32 Satellite Update Guide

After the security updates, your ESP32 satellite sensors need to be re-flashed with:
1. New MQTT password
2. Updated WiFi passwords (if changed)
3. New API encryption key (recommended)

---

## Prerequisites

- Mac with Docker installed
- USB-C cable
- ESP32 device

---

## Step 1: Get Latest Config from Storyteller

```bash
# Create working directory on Mac
mkdir -p ~/esphome-build && cd ~/esphome-build

# Copy current config from Storyteller
scp storyteller:greenhouse-beach/esphome/sensors/satellite-sensor-2.yaml .
scp storyteller:greenhouse-beach/esphome/secrets.yaml .
```

---

## Step 2: Verify/Update Credentials

Open `satellite-sensor-2.yaml` and verify these sections:

### MQTT Password (REQUIRED - Changed)
```yaml
mqtt:
  broker: 192.168.1.151   # For dev at your house
  # broker: 10.0.0.1      # For production at Mom's
  username: "greenhouse"
  password: "YOUR_NEW_MQTT_PASSWORD"  # Must match .env on Storyteller
```

### WiFi Passwords (If Changed)
```yaml
wifi:
  networks:
    - ssid: "GREENHOUSE_IOT"
      password: "YOUR_NEW_GREENHOUSE_WIFI"  # If changed
      priority: 10
    - ssid: "beachFi"
      password: "YOUR_NEW_BEACHFI_WIFI"     # If changed
      priority: 5
```

### API Key (Recommended: Regenerate)
```yaml
api:
  encryption:
    key: "NEW_KEY_HERE"  # Generate with: openssl rand -base64 32
```

Generate new key:
```bash
openssl rand -base64 32
# Copy output to the key field
```

---

## Step 3: Compile Firmware

```bash
cd ~/esphome-build

# Compile using Docker (no local install needed)
docker run --rm -v "$PWD":/config ghcr.io/esphome/esphome compile satellite-sensor-2.yaml
```

This creates: `satellite-sensor-2/.pioenvs/satellite-sensor-2/firmware.bin`

---

## Step 4: Flash the Device

### Option A: USB Flash (Device in Hand)

1. Connect ESP32 to Mac via USB-C
2. Open https://web.esphome.io in Chrome
3. Click **CONNECT**
4. Select the USB serial port (usually `cu.usbserial-*`)
5. Click **INSTALL**
6. Select the compiled `.bin` file from:
   ```
   ~/esphome-build/satellite-sensor-2/.pioenvs/satellite-sensor-2/firmware.bin
   ```
7. Wait for flash to complete

### Option B: OTA Flash (Device Already Deployed)

**Requires device to be awake and on same network!**

1. Enable maintenance mode to keep device awake:
   ```bash
   # On Storyteller
   docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
     -u greenhouse -P "YOUR_MQTT_PASSWORD" \
     -t 'greenhouse/satellite-2/maintenance/state' -m 'ON' -r
   ```

2. Wait for device to wake (up to 15 min)

3. Flash OTA:
   ```bash
   docker run --rm -v "$PWD":/config ghcr.io/esphome/esphome run satellite-sensor-2.yaml --device DEVICE_IP
   ```

4. **IMPORTANT:** Disable maintenance mode after:
   ```bash
   docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
     -u greenhouse -P "YOUR_MQTT_PASSWORD" \
     -t 'greenhouse/satellite-2/maintenance/state' -m 'OFF' -r
   ```

---

## Step 5: Verify Connection

```bash
# On Storyteller - watch for device messages
docker exec greenhouse-beach-mosquitto-1 mosquitto_sub \
  -u greenhouse -P "YOUR_MQTT_PASSWORD" \
  -t 'greenhouse/satellite-2/#' -v
```

Expected output when device wakes:
```
greenhouse/satellite-2/status online
greenhouse/satellite-2/sensor/satellite_2_temperature/state 22.5
greenhouse/satellite-2/sensor/satellite_2_humidity/state 65.2
greenhouse/satellite-2/sensor/satellite_2_battery/state 3.85
greenhouse/satellite-2/status offline
```

---

## Troubleshooting

### Device won't connect to WiFi
1. Double-check password in config
2. Ensure network is in range
3. Connect to rescue AP: `Satellite-2 Rescue` with rescue password

### MQTT connection refused
1. Verify MQTT password matches `.env` on Storyteller
2. Check Mosquitto is running: `docker ps | grep mosquitto`
3. Test connection: `mosquitto_pub -h IP -u greenhouse -P PASSWORD -t test -m hi`

### OTA fails with timeout
1. Device must be awake (enable maintenance mode)
2. Device must be on same network as your Mac
3. Try USB flash instead

---

## Quick Reference: Current Credentials Location

| Credential | Location |
|------------|----------|
| MQTT password | `~/.env` on Storyteller |
| WiFi passwords | `esphome/secrets.yaml` (gitignored) |
| API keys | In device YAML (gitignored) |

---

## After Flashing

1. [ ] Verify device connects to MQTT
2. [ ] Check sensor data appears in `status.json`
3. [ ] Disable maintenance mode if enabled
4. [ ] Test deep sleep cycle (device should sleep after ~60s)

---

*Last Updated: December 2024*
