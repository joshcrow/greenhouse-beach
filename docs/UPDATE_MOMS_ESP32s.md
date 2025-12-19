# 🔄 Updating ESP32s at Mom's House

This guide covers when and how to update the ESP32 sensors deployed at Mom's greenhouse.

---

## Do You Need to Update?

### ✅ YES - Update Required If:

| Change Made | Requires Re-Flash |
|-------------|-------------------|
| Changed MQTT password | **YES** |
| Changed GREENHOUSE_IOT WiFi password | **YES** |
| Changed ESPHome API key | **YES** |
| Updated sensor code/features | **YES** |

### ❌ NO - No Update Needed If:

- Only changed beachFi (dev) WiFi password
- Only updated documentation
- Only changed Storyteller-side code (Python scripts)

---

## Current MQTT Password Status

**If you updated the MQTT password on Storyteller**, the existing ESP32s will:
1. Connect to WiFi ✅
2. **FAIL to connect to MQTT** ❌
3. Keep retrying forever (or go to sleep and retry next cycle)

**Check if devices are connecting:**
```bash
# On Storyteller - watch for connection attempts
docker logs -f greenhouse-beach-mosquitto-1 2>&1 | grep -i "satellite\|auth"
```

---

## Update Options

### Option A: Update via OTA (Preferred - If WiFi Works)

**Requirements:**
- Device can connect to WiFi
- Device is on GREENHOUSE_IOT network
- You have network access (Tailscale or on-site)

**Steps:**

1. **Enable maintenance mode** (keeps device awake):
   ```bash
   # SSH to Storyteller
   docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
     -u greenhouse -P "YOUR_MQTT_PASSWORD" \
     -t 'greenhouse/satellite-2/maintenance/state' -m 'ON' -r
   ```
   
   > ⚠️ This only works if the device can still authenticate to MQTT!
   > If MQTT password changed, the device won't receive this message.

2. **Wait for device to wake** (up to 15 minutes)

3. **Flash OTA from Mac:**
   ```bash
   cd ~/esphome-build
   docker run --rm -v "$PWD":/config ghcr.io/esphome/esphome run satellite-sensor-2.yaml --device DEVICE_IP
   ```

4. **Disable maintenance mode after:**
   ```bash
   docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
     -u greenhouse -P "YOUR_MQTT_PASSWORD" \
     -t 'greenhouse/satellite-2/maintenance/state' -m 'OFF' -r
   ```

### Option B: Physical USB Flash (If OTA Not Possible)

**When to use:**
- MQTT password changed (device can't receive maintenance command)
- WiFi password changed (device can't connect)
- Device is unresponsive

**Steps:**

1. **Physically retrieve the ESP32** from the greenhouse

2. **On your Mac:**
   ```bash
   cd ~/esphome-build
   
   # Get latest config
   scp storyteller:greenhouse-beach/esphome/sensors/satellite-sensor-2.yaml .
   
   # Compile
   docker run --rm -v "$PWD":/config ghcr.io/esphome/esphome compile satellite-sensor-2.yaml
   ```

3. **Connect ESP32 via USB-C**

4. **Flash via web.esphome.io:**
   - Open https://web.esphome.io in Chrome
   - Click **CONNECT** → Select USB port
   - Click **INSTALL** → Choose the `.bin` file from:
     ```
     ~/esphome-build/satellite-sensor-2/.pioenvs/satellite-sensor-2/firmware.bin
     ```

5. **Verify before redeploying:**
   ```bash
   # Watch MQTT while device is connected to USB
   docker exec greenhouse-beach-mosquitto-1 mosquitto_sub \
     -u greenhouse -P "YOUR_MQTT_PASSWORD" \
     -t 'greenhouse/satellite-2/#' -v
   ```

6. **Redeploy to greenhouse**

---

## Bulk Update Checklist

If updating multiple devices:

- [ ] satellite-sensor-2 (exterior)
- [ ] Any other ESP32s you've deployed

**For each device:**
1. [ ] Update YAML with new credentials
2. [ ] Compile firmware
3. [ ] Flash (OTA or USB)
4. [ ] Verify MQTT messages appear on Storyteller
5. [ ] Redeploy to location

---

## Verifying Successful Update

After flashing, check the device is working:

```bash
# On Storyteller
docker exec greenhouse-beach-mosquitto-1 mosquitto_sub \
  -u greenhouse -P "YOUR_MQTT_PASSWORD" \
  -t 'greenhouse/+/#' -v
```

**Expected output when device wakes:**
```
greenhouse/satellite-2/status online
greenhouse/satellite-2/sensor/satellite_2_temperature/state 22.5
greenhouse/satellite-2/sensor/satellite_2_humidity/state 65.2
greenhouse/satellite-2/sensor/satellite_2_pressure/state 1013.25
greenhouse/satellite-2/sensor/satellite_2_battery/state 3.85
greenhouse/satellite-2/status offline
```

---

## Troubleshooting

### Device connects to WiFi but not MQTT
- **Cause:** MQTT password mismatch
- **Fix:** Re-flash with correct password

### Device doesn't connect to WiFi
- **Cause:** WiFi password changed
- **Fix:** Re-flash with correct WiFi password
- **Temporary:** Connect to rescue AP (`Satellite-2 Rescue`)

### Device visible but data not appearing
- **Check:** NAT forwarding on Greenhouse Pi
  ```bash
  # On Greenhouse Pi
  sudo iptables -t nat -L -n | grep 1883
  ```

### OTA update times out
- **Cause:** Device sleeping
- **Fix:** Enable maintenance mode OR use USB flash

---

## WiFi Password Reference

Your config should have:
```yaml
wifi:
  networks:
    - ssid: "GREENHOUSE_IOT"
      password: "YOUR_ACTUAL_GREENHOUSE_WIFI_PASSWORD"  # ← Update this
      priority: 10
    - ssid: "beachFi"
      password: "YOUR_ACTUAL_BEACHFI_PASSWORD"          # ← Keep for backup
      priority: 5
```

**Priority 10 > Priority 5**, so GREENHOUSE_IOT will be used when available.

---

*Last Updated: December 2024*
