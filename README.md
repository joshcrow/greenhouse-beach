# 🌱 The Greenhouse Gazette

**An autonomous, AI-powered daily newsletter for greenhouse monitoring.**

Transform passive greenhouse monitoring into an active, narrative-driven experience. The Greenhouse Gazette ingests environmental metrics and imagery from distributed sensors, then generates a daily email newsletter with a witty, scientific personality.

![Architecture](https://img.shields.io/badge/Architecture-Distributed_Edge-green)
![AI](https://img.shields.io/badge/AI-Gemini_3_Flash-blue)
![Platform](https://img.shields.io/badge/Platform-Raspberry_Pi-red)

---

## 📬 What You Get

**Daily Email (7:00 AM)**
- **AI-Generated Narrative** – Witty, scientific commentary on conditions
- **Comic Relief** – Daily joke or riddle (dry, observational humor about gardening)
- **Hero Image** – Photo captured at golden hour (optimal lighting)
- **Sensor Dashboard** – Interior, exterior, and satellite readings with battery status
- **Weather Forecast** – Today's conditions and tomorrow's outlook
- **24-Hour Stats** – High/low temperature and humidity trends

**Weekly Edition (Sundays 7:00 AM)**
- Everything from the daily email, plus:
- **Week Summary** – Temperature and humidity ranges with averages
- **Timelapse GIF** – Animated loop of all photos from the past week
- **📊 Weekly Edition** – Subject line clearly marked

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Home Network (beachFi)                      │
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────────────┐ │
│  │  Storyteller Pi  │              │    Greenhouse Pi         │ │
│  │  (Raspberry Pi 5)│              │    (Raspberry Pi 4)      │ │
│  │                  │              │                          │ │
│  │  Docker:         │◄─── MQTT ───►│  - Home Assistant        │ │
│  │  - mosquitto     │              │  - Camera Stream         │ │
│  │  - storyteller   │              │  - ESPHome               │ │
│  │                  │              │  - hostapd (IoT AP)      │ │
│  └──────────────────┘              └───────────┬──────────────┘ │
│                                                │                 │
└────────────────────────────────────────────────┼─────────────────┘
                                                 │ GREENHOUSE_IOT
                                                 ▼ (10.0.0.0/24)
                              ┌──────────────────────────────────┐
                              │        Satellite Sensors         │
                              │    (ESP32 + BME280 + Solar)      │
                              └──────────────────────────────────┘
```

### Components

| Node | Hardware | Role |
|------|----------|------|
| **Storyteller** | Raspberry Pi 5 | MQTT broker, AI narrative engine, email dispatch |
| **Greenhouse Pi** | Raspberry Pi 4 | Camera, Home Assistant, IoT gateway |
| **Satellites** | ESP32 (FireBeetle) | Battery/solar-powered environmental sensors |

---

## 🚀 Quick Start

### Prerequisites

- Raspberry Pi 5 (Storyteller) with Docker installed
- Raspberry Pi with Home Assistant and camera (Greenhouse Pi)
- ESP32 sensor nodes with ESPHome
- API Keys: Google Gemini, OpenWeatherMap (One Call 3.0)
- Gmail account with App Password for SMTP

### 1. Clone and Configure

```bash
git clone https://github.com/joshcrow/greenhouse-beach.git
cd greenhouse-beach
cp .env.example .env
nano .env  # Add your API keys and SMTP credentials
```

### 2. Start the Storyteller

```bash
# Option A: Pull pre-built image from Docker Hub (fast)
docker pull jcrow333/greenhouse-storyteller:latest
docker compose up -d

# Option B: Build locally
docker compose build
docker compose up -d

# Watch logs
docker compose logs -f
```

### 3. Deploy Bridges to Greenhouse Pi

```bash
# Copy bridge scripts
scp scripts/camera_mqtt_bridge.py scripts/ha_sensor_bridge.py user@greenhouse-pi:/opt/greenhouse/

# Install as services (see DEPLOYMENT.md for details)
```

### 4. Test Email Delivery

```bash
docker exec greenhouse-storyteller python scripts/publisher.py
```

---

## 🔄 CI/CD Pipeline

Automated testing and deployment via GitHub Actions.

| Component | Status |
|-----------|--------|
| **Docker Hub** | [`jcrow333/greenhouse-storyteller`](https://hub.docker.com/r/jcrow333/greenhouse-storyteller) |
| **CI/CD** | GitHub Actions (test → build → push) |
| **Platforms** | `linux/amd64`, `linux/arm64` (Raspberry Pi) |

### Development Workflow

```bash
# Run tests locally
pytest

# Push to trigger CI/CD
git push origin main
# → Tests run → Docker image built → Pushed to Docker Hub

# Update Storyteller Pi
ssh pi@storyteller
docker pull jcrow333/greenhouse-storyteller:latest
docker compose up -d
```

See [`DEVELOPMENT.md`](DEVELOPMENT.md) for full details.

---

## 📁 Project Structure

```
greenhouse-beach/
├── docker-compose.yml      # Orchestrates mosquitto + storyteller
├── Dockerfile              # Python 3.11 + OpenCV + Gemini SDK
├── .env.example            # Template for secrets
│
├── configs/
│   ├── mosquitto.conf      # MQTT broker config
│   └── registry.json       # Device registry and network topology
│
├── scripts/
│   ├── entrypoint.sh       # Launches all storyteller processes
│   ├── ingestion.py        # MQTT → image files
│   ├── curator.py          # Image quality filtering + archival
│   ├── status_daemon.py    # Sensor data aggregation + 24h stats
│   ├── narrator.py         # Gemini AI narrative generation
│   ├── publisher.py        # HTML email composition + SMTP
│   ├── scheduler.py        # Daily (7AM) + weekly (Sunday 8AM) dispatch
│   ├── weekly_digest.py    # Weekly summary email generation
│   ├── golden_hour.py      # Seasonal sunset calculations
│   ├── weather_service.py  # OpenWeatherMap integration
│   ├── stats.py            # 24-hour min/max calculations
│   │
│   │ # Greenhouse Pi bridges (deploy separately)
│   ├── camera_mqtt_bridge.py   # HA camera → MQTT
│   ├── ha_sensor_bridge.py     # HA sensors → MQTT
│   └── gateway_nat_setup.sh    # NAT for IoT network
│
├── data/
│   ├── status.json         # Latest sensor readings
│   ├── stats_24h.json      # 24-hour min/max stats
│   ├── incoming/           # Temporary image storage
│   └── archive/            # Archived images (YYYY/MM/DD/)
│
├── esphome/                # ESP32 sensor configurations
│   ├── sensors/            # Active device configs
│   ├── templates/          # Copy to create new sensors
│   └── secrets.yaml        # WiFi/MQTT credentials
│
└── docs/
    ├── DEPLOYMENT.md       # Installation guide
    ├── MASTER_DOCS.md      # Full system specification
    ├── CURRENT_STATE.md    # Live system status
    └── build-phase-*.md    # Hardware assembly guides
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# AI Narrative Engine
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash

# Weather API
OPENWEATHER_API_KEY=your-openweather-key
WEATHER_LAT=36.022
WEATHER_LON=-75.720

# Email (Gmail with App Password)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=Greenhouse Gazette <your-email@gmail.com>
SMTP_TO=recipient@example.com

# Timezone
TZ=America/New_York
```

### Device Registry (configs/registry.json)

Define your sensors, cameras, and network topology:

```json
{
  "site": {
    "name": "Outer Banks Greenhouse",
    "timezone": "America/New_York"
  },
  "devices": [
    {
      "type": "sensor_node",
      "device_name": "satellite_sensor_2",
      "topic_root": "greenhouse/satellite-2",
      "sensors": [
        {"key": "satellite_2_temperature", "unit": "°C"},
        {"key": "satellite_2_humidity", "unit": "%"}
      ]
    }
  ]
}
```

---

## 📡 Data Flow

```
1. Sensors publish to MQTT:
   greenhouse/{device}/sensor/{key}/state → mosquitto:1883

2. Status daemon aggregates:
   MQTT messages → status.json + stats_24h.json

3. Camera bridge captures:
   Home Assistant camera → MQTT → ingestion.py → archive/

4. Golden hour capture (seasonal timing):
   Camera bridge captures at optimal lighting (~4PM Dec, ~7PM June)

5. Scheduler triggers at 7:00 AM:
   scheduler.py → publisher.run_once() + weekly_digest.record_daily_snapshot()

6. Publisher builds email:
   status.json + weather API + Gemini AI → HTML email → SMTP

7. Weekly digest (Sundays 8:00 AM):
   weekly_digest.py aggregates week's data → summary email
```

---

## 🔧 Troubleshooting

### No sensor data in email
```bash
# Check status.json has data
cat data/status.json

# Verify MQTT messages arriving
docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t "greenhouse/#" -v
```

### Email not sending
```bash
# Test manually
docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py

# Check SMTP credentials in .env
```

### Camera images not arriving
```bash
# Check camera bridge on Greenhouse Pi
ssh user@greenhouse-pi "journalctl -u camera-mqtt-bridge -f"

# Test camera capture
ssh user@greenhouse-pi "python3 /opt/greenhouse/camera_mqtt_bridge.py --test"
```

### Satellite sensor offline
- Check battery voltage (should be > 3.4V actual, > 1.7V ADC with voltage divider)
- Verify WiFi connectivity to GREENHOUSE_IOT network
- Check ESPHome logs in Home Assistant

---

## 🔋 Hardware Notes

### FireBeetle 2 ESP32-E (Satellite Sensor)
- **Green LED**: Hardwired charging indicator (cannot disable in software)
- **Blue LED**: User LED on IO2 (disable in ESPHome)
- **Battery**: Uses 1/2 voltage divider. ADC reading of 1.7V = 3.4V actual

### Power Management
- Satellites use deep sleep between readings
- "Persistent" sensors in Home Assistant hold last value during sleep
- Email gracefully hides offline sensors (no "N/A" rows)

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) | **On-site deployment guide with test plan** |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Step-by-step initial setup |
| [MASTER_DOCS.md](MASTER_DOCS.md) | Full system specification and requirements |
| [CURRENT_STATE.md](CURRENT_STATE.md) | Live system status and verification |
| [esphome/README.md](esphome/README.md) | **ESPHome sensor configs & templates** |
| [ESP32-solar-guide.md](ESP32-solar-guide.md) | Solar-powered sensor build guide |

---

## 🛣️ Roadmap

- [ ] Microclimate analysis with multiple sensor zones
- [x] Weekly Edition with timelapse ✓
- [x] Golden hour photo capture ✓
- [x] Timelapse GIF generation ✓
- [ ] Web dashboard (real-time sensor view)
- [ ] Object detection for plant health
- [ ] Full timelapse video export

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- **Google Gemini** for AI narrative generation
- **OpenWeatherMap** for weather data
- **Eclipse Mosquitto** for MQTT brokering
- **ESPHome** for ESP32 sensor firmware
- **Home Assistant** for home automation integration

---

*Built with 🌿 for greenhouse enthusiasts who want their plants to have a voice.*
