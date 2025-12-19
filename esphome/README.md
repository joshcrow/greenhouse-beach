# 🔌 ESPHome Sensor Configurations

Centralized management for all ESPHome-based sensors in the Greenhouse Gazette system.

---

## 📁 Directory Structure

```
esphome/
├── README.md           # This file
├── secrets.yaml        # WiFi passwords, API keys (careful with git!)
├── sensors/            # Active device configurations
│   └── satellite-sensor-2.yaml
├── templates/          # Copy these to create new devices
│   └── battery-sensor-template.yaml
└── common/             # Shared includes (future use)
```

---

## 🚀 Quick Start: Create a New Sensor

### 1. Copy the Template
```bash
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
cd esphome/sensors
esphome compile satellite-sensor-3.yaml --only-generate
# Copy the generated key to the config
```

### 4. Flash the Device
```bash
# First time (via USB)
esphome run satellite-sensor-3.yaml

# Subsequent updates (OTA)
esphome run satellite-sensor-3.yaml --device 10.0.0.X
```

---

## 📊 Active Sensors

| Device | Location | Network | MQTT Topic | Status |
|--------|----------|---------|------------|--------|
| satellite-sensor-2 | Greenhouse exterior | GREENHOUSE_IOT | `greenhouse/satellite-2/#` | ✅ Active |

---

## 🔧 Development Workflow

### Local Development (at home)
```bash
# Connect to your local network, MQTT points to Storyteller
esphome run sensors/satellite-sensor-2.yaml
```

### Production Deployment (at Mom's)
1. Update `mqtt.broker` to `10.0.0.1`
2. Flash via OTA: `esphome run config.yaml --device 10.0.0.20`

### Remote Updates (from anywhere)
```bash
# Via Tailscale to Greenhouse Pi's network
esphome run sensors/satellite-sensor-2.yaml --device 10.0.0.20
```

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

## 🐛 Troubleshooting

### Device won't connect to WiFi
1. Check WiFi credentials in secrets.yaml
2. Verify network is in range
3. Connect to rescue AP: `Satellite-N Rescue` / `YOUR_RESCUE_AP_PASSWORD`

### MQTT messages not arriving
1. Check broker IP (dev vs production)
2. Verify Mosquitto is running on Storyteller
3. Test with: `mosquitto_sub -h IP -t "greenhouse/#" -v`

### Device keeps sleeping (can't OTA update)
1. Enable maintenance mode in Home Assistant
2. Or publish to MQTT: `greenhouse/satellite-N/maintenance/state` → `ON`

### Battery reading incorrect
1. Verify `multiply: 2.0` filter is present
2. Check physical connection to GPIO 36
3. Expected range: 1.5V - 2.1V (ADC), 3.0V - 4.2V (actual)

---

## 📝 Changelog

### 2025-12-19
- Initial setup of ESPHome config management
- Added satellite-sensor-2 config
- Created battery-sensor template
- Added secrets.yaml

---

*Part of [The Greenhouse Gazette](../README.md)*
