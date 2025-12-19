# 🔌 ESPHome Sensor Configurations

Centralized management for all ESPHome-based sensors in the Greenhouse Gazette system.

**Development Workflow:** Edit configs here (version controlled) → Sync to Mac → Compile & Flash from Mac

---

## 📁 Directory Structure

```
esphome/
├── README.md                        # This file
├── secrets.yaml                     # ⚠️ GITIGNORED - Your real credentials
├── secrets.example.yaml             # Template with placeholders
├── sensors/
│   ├── satellite-sensor-2.yaml      # ⚠️ GITIGNORED - Your real config
│   └── satellite-sensor-2.example.yaml  # Template with placeholders
├── templates/
│   └── battery-sensor-template.yaml # Template for new sensors
└── common/                          # Shared includes (future use)
```

> **Security:** Real configs with credentials are gitignored. Only `.example.yaml` files are committed.

**Related Documentation:**
- [ESP32-solar-guide.md](../ESP32-solar-guide.md) - Hardware soldering & assembly
- [ESP32-solar-guide-build](../ESP32-solar-guide-build) - Complete build guide with YAML
- [build-phase-1.md](../build-phase-1.md) - Pi infrastructure & first sensor
- [build-phase-2.md](../build-phase-2.md) - Adding soil, light sensors, camera

---

## � Development Workflow (Mac-Based)

> **Important:** Compiling on the Storyteller Pi takes forever due to SD card I/O.
> All compiling and flashing is done on your Mac.

### Setup: ESPHome on Mac

```bash
# Option 1: Install ESPHome directly
pip install esphome

# Option 2: Use Docker (recommended)
# No install needed - just use the docker commands below
```

### Workflow: Edit → Sync → Compile → Flash

```bash
# 1. Edit config on Storyteller (via SSH or Windsurf Remote)
ssh storyteller
cd greenhouse-beach/esphome/sensors
nano satellite-sensor-2.yaml

# 2. Commit changes
git add -A && git commit -m "Update satellite config" && git push

# 3. Sync to Mac
cd ~/Desktop/esphome-build  # Or wherever you keep configs
git pull  # If using the repo
# OR manually copy:
scp storyteller:greenhouse-beach/esphome/sensors/*.yaml .

# 4. Compile on Mac (Docker method - no install needed)
docker run --rm -v "$PWD":/config ghcr.io/esphome/esphome compile satellite-sensor-2.yaml

# 5. Flash via USB (first time)
#    - Connect ESP32 via USB
#    - Go to https://web.esphome.io
#    - Click Connect → Install → Select .bin file from .esphome/build/*/firmware.bin

# 5b. Flash via OTA (subsequent updates - device must be on network)
docker run --rm -v "$PWD":/config ghcr.io/esphome/esphome run satellite-sensor-2.yaml --device 10.0.0.20
```

---

## � Quick Start: Create a New Sensor

### 1. Copy the Template
```bash
# On Storyteller
cd ~/greenhouse-beach/esphome
cp templates/battery-sensor-template.yaml sensors/satellite-sensor-3.yaml
```

### 2. Customize the Config
Edit the `substitutions:` section at the top:

```yaml
substitutions:
  device_name: satellite-sensor-3        # Must be unique!
  friendly_name: "Satellite 3"
  sensor_prefix: "Satellite 3"
  mqtt_prefix: "greenhouse/satellite-3"
  maintenance_entity: input_boolean.greenhouse_satellite_3_maintenance
  rescue_ap_name: "Satellite-3 Rescue"
```

### 3. Generate a New API Key
```bash
# On Mac
openssl rand -base64 32
# Paste output into the api.encryption.key field
```

### 4. Compile & Flash (on Mac)
```bash
cd ~/Desktop/esphome-build
scp storyteller:greenhouse-beach/esphome/sensors/satellite-sensor-3.yaml .

# Compile
docker run --rm -v "$PWD":/config ghcr.io/esphome/esphome compile satellite-sensor-3.yaml

# Flash via USB (hold BOOT button if connection hangs)
# Go to https://web.esphome.io → Connect → Install → Select .bin file
```

### 5. Commit to Repo
```bash
# On Storyteller
cd ~/greenhouse-beach
git add esphome/sensors/satellite-sensor-3.yaml
git commit -m "Add satellite-sensor-3"
git push
```

---

## 📊 Active Sensors

| Device | Location | Network | MQTT Topic | Status |
|--------|----------|---------|------------|--------|
| satellite-sensor-2 | Greenhouse exterior | GREENHOUSE_IOT | `greenhouse/satellite-2/#` | ✅ Active |

---

## � Hardware Build Guide (Summary)

For detailed step-by-step instructions, see [ESP32-solar-guide.md](../ESP32-solar-guide.md).

### Bill of Materials
| Component | Part | Notes |
|-----------|------|-------|
| Controller | FireBeetle 2 ESP32-E (DFR0654) | Built-in LiPo charging |
| Battery | Li-Ion 3.7V 2.5Ah | Flat pack fits in enclosure |
| Enclosure | Gray Box 4.53" x 2.56" | Waterproof, use PG7 glands |
| Sensor | BME280 (I2C) | Temp/humidity/pressure |
| Power | 6V 1W Solar Panel | Mounts facing south @ 45° |

### Wiring (Solder to BOTTOM of FireBeetle)

```
Solar Panel:
  Red (+)  → VIN pad
  Black (-) → GND pad

BME280 Sensor:
  VCC → 3V3
  GND → GND
  SCL → Pin 22
  SDA → Pin 21
```

### Assembly Checklist
- [ ] Drill two 12.5mm holes in box bottom
- [ ] Install PG7 cable glands
- [ ] Route solar cable through gland #1
- [ ] Route sensor cable through gland #2
- [ ] Secure battery with foam tape (rotate 90°)
- [ ] Place insulation tape on top of battery
- [ ] Connect battery JST to ESP32
- [ ] Seal glands and close lid

### Mounting
- **Solar panel:** Face south, 45° tilt
- **Enclosure:** **MUST BE SHADED** (under panel or eaves)
- **Sensor:** Inside radiation shield if possible

---

## 🔄 Development vs Production Config

### At Your House (Development)
```yaml
mqtt:
  broker: 192.168.1.151   # Storyteller on your home network
```
Satellite connects to `beachFi` (priority 5).

### At Mom's House (Production)
```yaml
mqtt:
  broker: 10.0.0.1        # Greenhouse Pi (NATs to Storyteller)
```
Satellite connects to `GREENHOUSE_IOT` (priority 10).

### Switching Between Environments
The WiFi config already handles this with priorities:
```yaml
wifi:
  networks:
    - ssid: "GREENHOUSE_IOT"    # Production - Priority 10
      password: !secret wifi_password_production
      priority: 10
    - ssid: "beachFi"           # Development - Priority 5
      password: !secret wifi_password_dev
      priority: 5
```

Only the `mqtt.broker` needs to change between dev/prod.

> **Note:** Real passwords are in `secrets.yaml` (gitignored). See `secrets.example.yaml` for template.

---

## 🛠️ Hardware Reference

### FireBeetle 2 ESP32-E Pinout

| Function | Pin | Notes |
|----------|-----|-------|
| I2C SDA | GPIO 21 | BME280 data |
| I2C SCL | GPIO 22 | BME280 clock |
| Battery ADC | GPIO 36 (VP) | Has 1/2 voltage divider |
| User LED | GPIO 2 | Blue LED (can disable) |
| Charging LED | — | Green, hardwired (can't disable) |

### Battery Voltage Interpretation

| ADC Reading | Actual Voltage | Status |
|-------------|----------------|--------|
| 2.1V | 4.2V | Full |
| 1.85V | 3.7V | Good |
| 1.7V | 3.4V | Low |
| < 1.5V | < 3.0V | Critical! |

> **Note:** The multiply: 2.0 filter in the config compensates for the voltage divider.

---

## 🔐 Secrets Management

The `secrets.yaml` file contains:
- WiFi credentials for both networks
- MQTT credentials
- API encryption keys
- OTA passwords

**Option 1: Keep in repo (current)**
- Convenient for private repos
- All configs in one place

**Option 2: Gitignore secrets (more secure)**
```bash
echo "esphome/secrets.yaml" >> .gitignore
```
Then manage secrets separately.

---

## ✅ Verification & Testing

### Monitor MQTT Data Flow
```bash
# On Storyteller - watch all satellite data
ssh storyteller "docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t 'greenhouse/satellite-2/#' -v"

# Expected output when device wakes:
# greenhouse/satellite-2/status online
# greenhouse/satellite-2/sensor/satellite_2_temperature/state 19.5
# greenhouse/satellite-2/sensor/satellite_2_humidity/state 65.2
# greenhouse/satellite-2/sensor/satellite_2_battery/state 3.85
# greenhouse/satellite-2/status offline  (when it sleeps)
```

### Emergency Maintenance Mode (Keep Awake)
```bash
# Enable - device will stay awake for debugging/OTA
ssh storyteller "docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
  -t 'greenhouse/satellite-2/maintenance/state' -m 'ON' -r"

# Disable - IMPORTANT: Run this when done or battery will drain!
ssh storyteller "docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
  -t 'greenhouse/satellite-2/maintenance/state' -m 'OFF' -r"
```

### Check Device IP (on Greenhouse Pi)
```bash
# See DHCP leases for GREENHOUSE_IOT network
ssh greenhouse-pi "cat /var/lib/NetworkManager/dnsmasq-wlan0.leases"
```

---

## 🐛 Troubleshooting

### Device won't connect to WiFi
1. Check WiFi credentials in config
2. Verify network is in range
3. Connect to rescue AP: `Satellite-N Rescue` / `YOUR_RESCUE_AP_PASSWORD`
4. Check ESPHome logs via USB: `esphome logs satellite-sensor-2.yaml`

### MQTT messages not arriving
1. Check broker IP matches environment (dev: 192.168.1.151, prod: 10.0.0.1)
2. Verify Mosquitto is running: `docker ps | grep mosquitto`
3. Test subscription: `mosquitto_sub -h <IP> -t "greenhouse/#" -v`
4. Check NAT routing on Greenhouse Pi (production only)

### Device keeps sleeping (can't OTA update)
1. Enable maintenance mode via MQTT (see above)
2. Or via Home Assistant: Toggle `input_boolean.greenhouse_satellite_2_maintenance`
3. Wait for next wake cycle (up to 15 min)

### Battery reading incorrect
1. Verify `multiply: 2.0` filter is in config
2. Check physical connection to GPIO 36 (VP pin)
3. Expected ADC range: 1.5V - 2.1V → Actual: 3.0V - 4.2V
4. Reading 0.42V? Battery is dead or divider not applied

### OTA update fails
1. Device must be awake (enable maintenance mode first)
2. Device must be on same network as your Mac
3. For production: Use Tailscale or update via Home Assistant/ESPHome dashboard

---

## 📝 Changelog

### 2025-12-19
- Initial setup of ESPHome config management
- Added satellite-sensor-2 config (from working deployment)
- Created battery-sensor template with substitutions
- Added secrets.yaml for centralized credentials
- Documented Mac-based compile/flash workflow
- Added hardware build summary with wiring diagram
- Integrated existing ESP32 build guides
- Added MQTT verification and maintenance mode commands

---

*Part of [The Greenhouse Gazette](../README.md)*
