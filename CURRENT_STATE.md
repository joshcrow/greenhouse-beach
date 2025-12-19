# Project Chlorophyll: Current System State

**Status:** ✅ Operational (via Tailscale) — Ready for Deployment  
**Last Updated:** Dec 19, 2025 @ 6:40 PM EST  
**Next Milestone:** Deploy FireBeetle at Mom's greenhouse (Dec 20)

---

## 🚀 CI/CD Pipeline (NEW)

| Component | Status |
|-----------|--------|
| **GitHub Repo** | [joshcrow/greenhouse-beach](https://github.com/joshcrow/greenhouse-beach) |
| **Docker Hub** | [jcrow333/greenhouse-storyteller](https://hub.docker.com/r/jcrow333/greenhouse-storyteller) |
| **CI/CD** | GitHub Actions ✅ |
| **Tests** | 104 passed, 10 skipped (41% coverage) |

### Development Workflow
```bash
# 1. Edit code locally
# 2. Test: pytest
# 3. Push: git push
# 4. GitHub Actions runs tests → builds Docker → pushes to Hub
```

### Deploy to Pi (Fast!)
```bash
docker pull jcrow333/greenhouse-storyteller:latest
docker compose up -d
```

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
| `satellite-2` | Ready for deploy | 21.2°C | ✅ Flashed & tested |
| `satellite-2_battery` | FireBeetle | 4.2V | ✅ Fully charged |
| `sensor1_greenhouse` | Broken hardware | — | ❌ Offline |

> ✅ **FireBeetle satellite flashed and tested!** Battery at 4.2V (100%). Ready for greenhouse deployment.

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
- [x] **Battery column** - Color-coded battery status in sensor table
- [x] **Battery alerts** - AI mentions battery only when critical (<3.4V)
- [x] **Email dispatch** - Gmail SMTP with App Password
- [x] **Hero image** - Latest archived image embedded in email
- [x] **7AM scheduler** - Running and ready for tomorrow
- [x] **Weekly Edition** - Sunday daily email includes weekly summary + timelapse GIF
- [x] **Timelapse generation** - Animated GIF from week's archived images
- [x] **Golden hour capture** - Seasonal timing for optimal photos (Dec: 3:45 PM)

---

## 📋 Pending Tasks

### Pre-Work (Do NOW Before Leaving)
- [x] Add BeachFi WiFi credentials to Storyteller ✅
- [x] Verify Tailscale is enabled and auto-starts ✅
- [x] Satellite ESPHome has dual-network support ✅
- [x] Helper scripts created (set_static_ip.sh, update_bridge_configs.sh) ✅
- [x] Charge satellite battery to full ✅ (4.2V = 100%)
- [x] Flash satellite with production MQTT broker (10.0.0.1) ✅
- [x] Fixed battery ADC pin (GPIO34) ✅
- [x] Verified battery operation via ping test ✅

### On-Site Installation (At Mom's)
- [ ] Connect Storyteller to beachFi network
- [ ] Set static IP (192.168.1.50)
- [ ] Update Greenhouse Pi bridge configs
- [ ] Configure NAT routing on Greenhouse Pi
- [ ] Deploy satellite sensor to greenhouse
- [ ] Run full test plan (see INSTALLATION_GUIDE.md)
- [ ] Verify remote access works from phone hotspot

### Future
- [ ] Fix sensor #1 hardware
- [ ] Add more microclimate sensors
- [x] NVMe migration (will dramatically speed up Docker builds) ✅
- [ ] Web dashboard

---

## 🔧 Quick Commands

```bash
# === CI/CD & Testing ===
pytest                                    # Run tests locally
pytest tests/test_publisher.py           # Run specific test
docker compose run --rm test             # Run tests in Docker
gh run list                              # Check CI status

# === Docker Operations ===
docker compose logs -f --tail 50         # Check Storyteller logs
docker compose up -d                     # Start production
docker compose --profile dev up          # Dev mode (hot-reload)
docker pull jcrow333/greenhouse-storyteller:latest  # Pull latest image

# === Manual Actions ===
docker exec greenhouse-storyteller python scripts/publisher.py  # Test email
cat data/status.json | jq                # Check sensor data

# === SSH to Greenhouse Pi ===
ssh joshcrow@100.110.161.42

# === Greenhouse Pi Services ===
ssh joshcrow@100.110.161.42 "systemctl status camera-mqtt-bridge ha-sensor-bridge --no-pager"
```