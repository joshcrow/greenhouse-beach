# Project Chlorophyll: Current System State

**Status:** ✅ Operational (via Tailscale) — Production-Hardened  
**Last Updated:** Dec 28, 2025 @ 6:15 PM EST  
**Next Milestone:** On-site deployment at Mom's house

---

## 🚀 CI/CD Pipeline (NEW)

| Component | Status |
|-----------|--------|
| **GitHub Repo** | [joshcrow/greenhouse-beach](https://github.com/joshcrow/greenhouse-beach) |
| **Docker Hub** | [jcrow333/greenhouse-storyteller](https://hub.docker.com/r/jcrow333/greenhouse-storyteller) |
| **CI/CD** | GitHub Actions ✅ |
| **Tests** | 109 passed, 8 skipped (49% coverage) |

### Development Workflow
```bash
# 1. Edit code locally
# 2. Test: pytest
# 3. Push: git push
# 4. GitHub Actions runs tests → builds Docker → pushes to Hub
```

### Deploy to Pi (Fast!)
```bash
# Local build (pull_policy: never)
docker compose build --no-cache storyteller
docker compose up -d --force-recreate storyteller
```

---

## 🖥️ Storyteller Pi (This Machine)

| Property | Value |
|----------|-------|
| **Hostname** | `greenhouse-storyteller` |
| **Location** | Josh's home network (192.168.1.151) |
| **Tailscale IP** | `100.94.172.114` |
| **Storage** | NVMe (1TB) ✅ |
| **Docker** | 2 containers running |

### Docker Services
| Container | Status | Purpose |
|-----------|--------|---------|
| `greenhouse-mosquitto` | ✅ Running | MQTT broker (port 1883) |
| `greenhouse-storyteller` | ✅ Running | 5 Python processes + web server |

### Storyteller Processes
| Process | Topic/Schedule | Status |
|---------|----------------|--------|
| `ingestion.py` | `greenhouse/+/image` | ✅ Receiving camera images |
| `curator.py` | Archive queue | ✅ Processing to `data/archive/` |
| `scheduler.py` | 07:00 daily, monthly/yearly timelapses | ✅ Running |
| `status_daemon.py` | `greenhouse/+/sensor/+/state` | ✅ Writing `status.json` + device monitoring |
| `device_monitor.py` | Every 5 min | ✅ Online/offline alerts via email |
| `web_server.py` | Port 8080 | ✅ Serving timelapses |

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
| `camera-mqtt-bridge` | 30 min | ✅ Publishing to Storyteller (fixed Dec 22) |
| `sensor-mqtt-bridge` | 5 min | ✅ Publishing HA sensors |
| Home Assistant | Always | ✅ Camera streaming |

---

## 📊 Active Sensors

| Sensor | Location | Last Value | Status |
|--------|----------|------------|--------|
| `interior_temp` | Greenhouse inside | — | ⚠️ Pi offline (solar) |
| `interior_humidity` | Greenhouse inside | — | ⚠️ Pi offline (solar) |
| `exterior_temp` | Greenhouse outside | — | ⚠️ Pi offline (solar) |
| `exterior_humidity` | Greenhouse outside | — | ⚠️ Pi offline (solar) |
| `satellite-2_battery` | FireBeetle | 4.0V | ✅ Reporting |
| `satellite-2_temp/humidity` | FireBeetle BME280 | — | ⚠️ Needs investigation |
| `sensor1_greenhouse` | Broken hardware | — | ❌ Offline |

> ⚠️ **Greenhouse Pi offline** since Dec 23 (solar battery depleted). Will auto-recover with sunlight.
> ⚠️ **FireBeetle BME280** not publishing temp/humidity (battery OK). Needs ESPHome investigation.

---

## ⚙️ Configuration Overrides

1. **Camera:** Hardware device mapping COMMENTED OUT - images via MQTT bridge
2. **MQTT:** Using legacy `mqtt.Client()` API for Paho 1.x/2.x compatibility
3. **AI Model:** `gemini-2.5-flash` primary, `gemini-2.0-flash-lite` fallback
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
- [x] **AI narrative** - Gemini 3 Flash with punchy prose (migrated to new google-genai SDK)
- [x] **Comic Relief** - Daily joke or riddle (thematically related to narrative, dry/observational tone)
- [x] **Riddle continuity** - Riddle answers revealed in next day's email (always riddle mode, no jokes)
- [x] **Bold alerts** - `<b>` tags render in email body (HTML version only, plain text stripped)
- [x] **Integer display** - All temps/humidity/wind rounded (no decimals)
- [x] **Urgency subjects** - Dynamic subject lines based on conditions
- [x] **Battery column** - Color-coded battery status in sensor table
- [x] **Battery alerts** - AI mentions battery only when critical (<3.4V)
- [x] **Email dispatch** - Gmail SMTP with App Password
- [x] **Hero image** - Latest archived image embedded in email
- [x] **7AM scheduler** - Running and ready for tomorrow
- [x] **Weekly Edition** - Sunday daily email includes weekly summary + timelapse GIF
- [x] **Daily timelapse** - 60-frame GIF of yesterday's daylight images in every email
- [x] **Weekly timelapse** - 100-frame GIF in Sunday edition
- [x] **Monthly timelapse** - 500-frame MP4 generated on 1st of month, email notification
- [x] **Yearly timelapse** - 4000-frame MP4 generated Jan 1st, email notification
- [x] **Timelapse web server** - http://100.94.172.114:8080/timelapses/
- [x] **Golden hour capture** - Seasonal timing for optimal photos (Dec: 3:45 PM)
- [x] **Coast & Sky integration** - NOAA tides (Jennette's Pier), meteor showers, named moon events
- [x] **Emoji policy** - No emojis in AI-generated subject/headline/body; kept in data tables
- [x] **Visibility gating** - clouds_pct, precip_prob for meteor shower recommendations
- [x] **Sensor data persistence** - History cache survives container restarts
- [x] **Long-term sensor logs** - Monthly JSONL files in `data/sensor_log/` for analysis
- [x] **Device monitoring** - Email alerts when greenhouse-pi or satellite-2 goes online/offline
- [x] **Sentence case** - All AI-generated subject lines and headlines use sentence case (not Title Case)
- [x] **Notable tides only** - Narrator only mentions king tides, negative tides, or >3.5ft tides
- [x] **Separate HTML/plain text** - Email body has proper HTML version and clean plain text version
- [x] **Sunrise/Sunset compact** - Combined into single row in weather table
- [x] **Production hardening** - Security audit complete (Dec 21):
  - Buffer overflow protection (sensor log cap)
  - Fail-fast API key validation
  - Data durability (fsync before atomic writes)
  - MQTT resource cleanup and timeout handling
  - Calendar JSON validation
  - Coast/sky cache persistence
- [x] **Enterprise refactor** - Reliability improvements (Dec 28):
  - Pydantic config (`app/config.py`) - centralized settings with fail-fast validation
  - Data models (`app/models.py`) - type-safe SensorSnapshot, WeatherData, EmailContent
  - VitalsFormatter service (`app/services/`) - extracted formatting logic
  - Tenacity retries - Weather API and NOAA API with exponential backoff (3 attempts)
  - Fixed Sunday email bug (`_test_mode` undefined when imported by scheduler)

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
- [x] **NVMe migration** - 1TB NVMe installed ✅
- [ ] Web dashboard
- [ ] Investigate FireBeetle BME280 not publishing (battery works, temp/humidity don't)

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
docker exec greenhouse-storyteller python scripts/publisher.py --test  # Test email (you only)
docker exec greenhouse-storyteller python scripts/publisher.py         # Full email (all recipients)
docker exec greenhouse-storyteller python scripts/device_monitor.py    # Check device online/offline status
cat data/status.json | jq                # Check sensor data

# === SSH to Greenhouse Pi ===
ssh joshcrow@100.110.161.42

# === Greenhouse Pi Services ===
ssh joshcrow@100.110.161.42 "systemctl status camera-mqtt-bridge ha-sensor-bridge --no-pager"
```