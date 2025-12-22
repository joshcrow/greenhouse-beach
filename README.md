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

**Hardware:**
- Raspberry Pi 4/5 (Storyteller) with 4GB+ RAM
- Raspberry Pi with Home Assistant and camera (Greenhouse Pi)
- ESP32 sensor nodes with ESPHome (optional)

**Software:**
- Docker Engine 24+ and Docker Compose V2
- Python 3.11+ (for local development only)
- Git

**API Keys (Required):**
| Service | Purpose | Get Key |
|---------|---------|----------|
| Google Gemini | AI narrative generation | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| OpenWeatherMap | Weather data (One Call 3.0) | [openweathermap.org](https://openweathermap.org/api) |
| Gmail App Password | Email delivery | [Google Account → Security → App passwords](https://myaccount.google.com/apppasswords) |

---

### Step 1: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/your-username/greenhouse-gazette.git
cd greenhouse-gazette

# Copy environment template
cp .env.example .env
```

### Step 2: Set Environment Variables

Edit `.env` with your credentials:

```bash
# Required - AI Narrative
GEMINI_API_KEY=your-gemini-api-key

# Required - Weather
OPENWEATHER_API_KEY=your-openweather-key
LAT=36.022                    # Your greenhouse latitude
LON=-75.720                   # Your greenhouse longitude

# Required - MQTT
MQTT_HOST=mosquitto
MQTT_PORT=1883
MQTT_USERNAME=greenhouse
MQTT_PASSWORD=your-mqtt-password

# Required - Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_TO=recipient@example.com

# Timezone
TZ=America/New_York
```

### Step 3: Configure MQTT Authentication

```bash
# Generate a strong password
openssl rand -base64 24

# Create the Mosquitto password file
docker run --rm -v $(pwd)/configs:/mosquitto/config eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/config/passwd greenhouse

# Enter the same password you put in .env when prompted
```

### Step 4: Build and Start

```bash
# Build the Docker image
docker compose build

# Start all services (mosquitto + storyteller)
docker compose up -d

# Verify services are running
docker compose ps

# Watch logs
docker compose logs -f
```

### Step 5: Deploy Camera Bridge to Greenhouse Pi

```bash
# Copy bridge scripts to Greenhouse Pi
scp scripts/camera_mqtt_bridge.py user@greenhouse-pi:/opt/greenhouse/
scp scripts/camera_mqtt_bridge.env user@greenhouse-pi:/opt/greenhouse/

# SSH to Greenhouse Pi and install dependencies
ssh user@greenhouse-pi
pip3 install paho-mqtt requests

# Edit environment file with your HA credentials
nano /opt/greenhouse/camera_mqtt_bridge.env

# Test camera capture
python3 /opt/greenhouse/camera_mqtt_bridge.py --test

# Run as daemon (or install as systemd service)
python3 /opt/greenhouse/camera_mqtt_bridge.py --daemon --interval 1800
```

### Step 6: Test the System

```bash
# Test email delivery manually
docker compose exec storyteller python scripts/publisher.py

# Check if images are being archived
ls -la data/archive/$(date +%Y)/$(date +%m)/$(date +%d)/

# Verify sensor data is being collected
cat data/status.json | python3 -m json.tool
```

---

## 🧪 Testing

### Run Tests Locally

```bash
# Install test dependencies
pip install -r requirements.txt

# Run full test suite (109 tests)
pytest

# Run with coverage report
pytest --cov=scripts --cov-report=term-missing

# Run specific test file
pytest tests/test_publisher.py -v

# Run tests in Docker
docker compose run --rm storyteller pytest tests/ -v
```

### Manual Component Tests

```bash
# Test MQTT connectivity
docker compose exec mosquitto mosquitto_sub -t "greenhouse/#" -v -u greenhouse -P yourpassword

# Test weather API
docker compose exec storyteller python -c "
import weather_service
print(weather_service.get_current_weather())
"

# Test Gemini AI
docker compose exec storyteller python -c "
import narrator
subj, head, body, data = narrator.generate_update({'interior_temp': 72, 'interior_humidity': 65})
print(f'Subject: {subj}')
print(f'Headline: {head}')
"

# Test SMTP connection
docker compose exec storyteller python -c "
import os, smtplib, ssl
ctx = ssl.create_default_context()
with smtplib.SMTP_SSL(os.getenv('SMTP_SERVER'), 465, context=ctx) as s:
    s.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
    print('✅ SMTP connection successful')
"
```

---

## 🔄 CI/CD Pipeline

Automated testing and deployment via GitHub Actions.

| Stage | Description |
|-------|-------------|
| **Quality** | Ruff linting + pytest (109 tests) |
| **Build** | Docker multi-arch image (amd64 + arm64) |
| **Security** | pip-audit dependency scan |
| **Deploy** | Push to Docker Hub on main branch |

### Development Workflow

```bash
# Run tests locally before pushing
pytest

# Push to trigger CI/CD
git push origin main
# → Lint → Test → Build → Push to Docker Hub

# Update production Pi
ssh user@storyteller-pi
cd /opt/greenhouse
docker compose pull
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

### Common Errors and Solutions

#### "GEMINI_API_KEY environment variable is not set"
```bash
# Verify .env is loaded
docker compose exec storyteller env | grep GEMINI

# Fix: Ensure .env exists and restart
cp .env.example .env
nano .env  # Add your API key
docker compose down && docker compose up -d
```

#### "MQTT connection failed with rc=5" (Authentication Error)
```bash
# rc=5 means bad username/password
# Verify password matches between .env and configs/passwd

# Regenerate password file
docker run --rm -v $(pwd)/configs:/mosquitto/config eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/config/passwd greenhouse
# Enter the EXACT password from your .env file

# Restart mosquitto
docker compose restart mosquitto
```

#### "Weather API unreachable or error occurred"
```bash
# Check API key validity
curl "https://api.openweathermap.org/data/3.0/onecall?lat=36&lon=-75&appid=YOUR_KEY"

# Common causes:
# - Invalid API key (check for typos)
# - One Call 3.0 not subscribed (free tier requires signup)
# - Rate limit exceeded (1000 calls/day free)
```

#### "No daylight images found for daily timelapse"
```bash
# Check if images exist for yesterday
ls -la data/archive/$(date -d yesterday +%Y)/$(date -d yesterday +%m)/$(date -d yesterday +%d)/

# If empty, verify camera bridge is running on Greenhouse Pi
ssh user@greenhouse-pi "ps aux | grep camera_mqtt"

# Check camera bridge logs
ssh user@greenhouse-pi "tail -50 /tmp/camera_bridge.log"
```

#### "Permission denied" on data directories
```bash
# Fix ownership (run on host, not in container)
sudo chown -R $(id -u):$(id -g) data/

# Or set permissions
chmod -R 755 data/
```

#### Images stuck in `incoming/` (not moving to `archive/`)
```bash
# Check curator logs for errors
docker compose logs storyteller | grep curator

# Common causes:
# - Image too dark (brightness < 10) → archived to _night/ folder
# - Image corrupt (cv2.imread fails) → deleted
# - Permissions issue → see above
```

#### Email sends but has no timelapse (static image instead)
```bash
# Timelapse requires ≥2 daylight images from yesterday
# Check archive
ls data/archive/$(date -d yesterday +%Y/%m/%d)/*.jpg | wc -l

# If < 2 images, timelapse falls back to latest static image
# This is expected behavior, not an error
```

#### Sensor values showing as "N/A" or missing
```bash
# Check status.json for recent data
cat data/status.json | python3 -m json.tool

# Verify MQTT messages arriving
docker compose exec mosquitto mosquitto_sub -t "greenhouse/#" -v -u greenhouse -P yourpassword

# Check status_daemon logs
docker compose logs storyteller | grep status
```

#### "Sensor value out of bounds" warnings
```bash
# Data validation rejects:
# - Temperature outside -10°F to 130°F
# - Humidity outside 0% to 100%
# - Sudden spikes (>20°F or >30% in 10 minutes)

# Check for faulty sensor or loose connection
# Verify ESPHome calibration if values seem wrong
```

### Diagnostic Commands

```bash
# View all running processes in storyteller container
docker compose exec storyteller ps aux

# Check container health
docker compose ps

# View recent logs (last 100 lines)
docker compose logs --tail=100 storyteller

# Inspect status.json
docker compose exec storyteller cat /app/data/status.json | python3 -m json.tool

# Check disk usage of archive
du -sh data/archive/

# Count images by day
for d in data/archive/2025/*/*; do echo "$d: $(ls $d/*.jpg 2>/dev/null | wc -l)"; done
```

### Performance Issues on Raspberry Pi

```bash
# Check memory usage
free -h

# If low memory, reduce timelapse size in scripts/timelapse.py:
# max_width=400, max_frames=30, colors=64

# Check SD card health (avoid excessive writes)
iostat -x 1 3

# Move data directory to external storage if needed
# Edit docker-compose.yml volumes section
```

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
