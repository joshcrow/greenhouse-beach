# Project Chlorophyll: Current System State

**Status:** ✅ Operational (via Tailscale)  
**Last Updated:** Dec 19, 2025 @ 11:35 AM EST

---

## 🖥️ Storyteller Pi (This Machine)

| Property | Value |
|----------|-------|
| **Hostname** | `greenhouse-storyteller` |
| **Location** | Josh's home network (192.168.1.151) |
| **Tailscale IP** | `100.94.172.114` |
| **Storage** | SD Card (NVMe migration pending) |
| **Docker** | 2 containers running |

### Docker Services
| Container | Status | Purpose |
|-----------|--------|---------|
| `greenhouse-beach-mosquitto-1` | ✅ Running | MQTT broker (port 1883) |
| `greenhouse-beach-storyteller-1` | ✅ Running | 4 Python processes |

### Storyteller Processes
| Process | Topic/Schedule | Status |
|---------|----------------|--------|
| `ingestion.py` | `greenhouse/+/image` | ✅ Receiving camera images |
| `curator.py` | Archive queue | ✅ Processing to `data/archive/` |
| `scheduler.py` | 07:00 EST daily | ✅ Triggering Daily Dispatch |
| `status_daemon.py` | `greenhouse/+/sensor/+/state` | ✅ Writing `status.json` |

---

## 🌿 Greenhouse Pi (Mom's House)

| Property | Value |
|----------|-------|
| **Hostname** | `greenhouse-pi` |
| **Location** | Mom's house (beachFi network) |
| **Tailscale IP** | `100.110.161.42` |
| **SSH** | Key auth configured ✅ |

### Services Running
| Service | Interval | Status |
|---------|----------|--------|
| `camera-mqtt-bridge` | 60 min | ✅ Publishing to Storyteller |
| `sensor-mqtt-bridge` | 5 min | ✅ Publishing HA sensors |
| Home Assistant | Always | ✅ Camera streaming |

---

## 📊 Active Sensors

| Sensor | Location | Last Value | Status |
|--------|----------|------------|--------|
| `interior_temp` | Greenhouse inside | 61°F | ✅ |
| `interior_humidity` | Greenhouse inside | 78% | ✅ |
| `exterior_temp` | Greenhouse outside | 72°F | ✅ |
| `exterior_humidity` | Greenhouse outside | 74% | ✅ |
| `satellite-2` | Josh's house (temp) | 66°F | ✅ |
| `satellite-2_battery` | Josh's house | 0.84V | ⚠️ **CRITICAL** |
| `sensor1_greenhouse` | Broken hardware | — | ❌ Offline |

> ⚠️ **Satellite battery is dead!** Reading 0.42V (actual 0.84V with divider). Charge immediately.

---

## ⚙️ Configuration Overrides

1. **Camera:** Hardware device mapping COMMENTED OUT - images via MQTT bridge
2. **MQTT:** Using `CallbackAPIVersion.VERSION2` for Paho 2.x
3. **AI Model:** `gemini-2.5-flash` primary, `gemini-flash-latest` fallback
4. **Weather:** OpenWeatherMap One Call 3.0 API
5. **Temps:** Auto-convert Celsius to Fahrenheit when < 50
6. **Sensor Keys:** Zone-prefixed format (`interior_temp`, `exterior_temp`)

---

## ✅ Verified Working

- [x] **Tailscale mesh** - Storyteller ↔ Greenhouse Pi ↔ MacBook
- [x] **Camera pipeline** - HA camera → MQTT → archive
- [x] **HA sensor bridge** - Interior + exterior sensors → MQTT
- [x] **Multi-zone email** - Interior, Exterior, Satellite rows
- [x] **Offline sensor handling** - Rows hidden when `None`
- [x] **Weather integration** - OpenWeatherMap One Call 3.0
- [x] **AI narrative** - Gemini 2.5 Flash with punchy prose
- [x] **Bold alerts** - `<b>` tags render in email body
- [x] **Integer display** - All temps/humidity/wind rounded (no decimals)
- [x] **Urgency subjects** - Dynamic subject lines based on conditions
- [x] **Email dispatch** - Gmail SMTP with App Password
- [x] **Hero image** - Latest archived image embedded in email
- [x] **7AM scheduler** - Running and ready for tomorrow

---

## 📋 Pending Tasks

### This Weekend (On-Site at Mom's)
- [ ] Move Storyteller Pi to beachFi network
- [ ] Set static IP (192.168.1.50)
- [ ] Update bridge configs: `sed -i 's/100.94.172.114/192.168.1.50/' /opt/greenhouse/*.env`
- [ ] Run NAT setup: `sudo /opt/greenhouse/gateway_nat_setup.sh 192.168.1.50`
- [ ] Relocate satellite sensor to greenhouse
- [ ] Charge FireBeetle battery (currently ~2.5V - critical!)

### Future
- [ ] Fix sensor #1 hardware
- [ ] Add more microclimate sensors
- [ ] NVMe migration
- [ ] Web dashboard

---

## 🔧 Quick Commands

```bash
# Check Storyteller status
docker compose logs -f --tail 50

# Trigger test email
docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py

# Check sensor data
cat data/status.json | jq

# SSH to Greenhouse Pi (no password needed)
ssh joshcrow@100.110.161.42

# Trigger sensor bridge manually
ssh joshcrow@100.110.161.42 "cd /opt/greenhouse && export \$(cat camera_mqtt_bridge.env | grep -v '^#' | xargs) && python3 ha_sensor_bridge.py"

# Check Greenhouse Pi services
ssh joshcrow@100.110.161.42 "systemctl status camera-mqtt-bridge sensor-mqtt-bridge --no-pager"
```