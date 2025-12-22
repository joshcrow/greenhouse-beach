# Greenhouse Gazette - System Architecture

> AI-powered greenhouse monitoring system with daily narrative emails, timelapse generation, and multi-node sensor aggregation.

---

## 1. System Overview

### What It Does

The **Greenhouse Gazette** (codename: Project Chlorophyll) is a distributed IoT monitoring system that:

1. **Captures** periodic photos from a greenhouse camera
2. **Collects** environmental sensor data (temperature, humidity, pressure)
3. **Aggregates** data from multiple nodes via MQTT
4. **Generates** AI-powered narrative emails with weather context
5. **Creates** animated timelapse GIFs/videos (daily, weekly, monthly, yearly)
6. **Delivers** a "morning newspaper" email at 7 AM daily

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Runtime** | Python 3.11, Docker (multi-arch: ARM64/AMD64) |
| **Messaging** | MQTT (Eclipse Mosquitto broker) |
| **AI/ML** | Google Gemini API (narrative generation) |
| **Image Processing** | OpenCV (headless), Pillow, FFmpeg |
| **Scheduling** | `schedule` library (cron-like) |
| **Email** | SMTP (Gmail) with embedded images |
| **External APIs** | OpenWeatherMap, NOAA CO-OPS (tides) |
| **CI/CD** | GitHub Actions → Docker Hub |

### Physical Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GREENHOUSE PI (Node A)                      │
│                         Mom's House                                 │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐    │
│  │  Home Assistant │   │ camera_mqtt_    │   │ ha_sensor_      │    │
│  │  (Camera)       │──▶│ bridge.py       │   │ bridge.py       │    │
│  └─────────────────┘   └────────┬────────┘   └────────┬────────┘    │
│                                 │ MQTT                │ MQTT        │
└─────────────────────────────────┼─────────────────────┼─────────────┘
                                  │                     │
                          ════════╧═════════════════════╧════════
                                    Tailscale VPN Mesh
                          ═══════════════════╤═══════════════════
                                             │
┌────────────────────────────────────────────┼────────────────────────┐
│                    STORYTELLER PI (Node B) │                        │
│                           House / Docker   ▼                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Docker Compose Stack                      │   │
│  │  ┌─────────────┐  ┌─────────────────────────────────────┐    │   │
│  │  │  Mosquitto  │  │       greenhouse-storyteller        │    │   │
│  │  │   (MQTT)    │◀─┤  ┌───────────┐  ┌───────────────┐   │    │   │
│  │  │  :1883      │  │  │ ingestion │  │ status_daemon │   │    │   │
│  │  └─────────────┘  │  └─────┬─────┘  └───────┬───────┘   │    │   │
│  │                   │        │                │           │    │   │
│  │                   │        ▼                ▼           │    │   │
│  │                   │  ┌───────────┐  ┌───────────────┐   │    │   │
│  │                   │  │  curator  │  │  status.json  │   │    │   │
│  │                   │  └─────┬─────┘  └───────────────┘   │    │   │
│  │                   │        │                            │    │   │
│  │                   │        ▼                            │    │   │
│  │                   │  ┌───────────┐  ┌───────────────┐   │    │   │
│  │                   │  │  archive/ │  │   scheduler   │   │    │   │
│  │                   │  │  (images) │  │   (7AM job)   │   │    │   │
│  │                   │  └───────────┘  └───────┬───────┘   │    │   │
│  │                   │                         │           │    │   │
│  │                   │                         ▼           │    │   │
│  │                   │                 ┌───────────────┐   │    │   │
│  │                   │                 │   publisher   │   │    │   │
│  │                   │                 │  + narrator   │   │    │   │
│  │                   │                 │  + timelapse  │   │    │   │
│  │                   │                 └───────┬───────┘   │    │   │
│  │                   │                         │           │    │   │
│  │                   └─────────────────────────┼───────────┘    │   │
│  └─────────────────────────────────────────────┼────────────────┘   │
│                                                │                    │
└────────────────────────────────────────────────┼────────────────────┘
                                                 │ SMTP
                                                 ▼
                                        ┌───────────────┐
                                        │  Gmail SMTP   │
                                        │  Recipients   │
                                        └───────────────┘
```

---

## 2. Directory Structure

```
greenhouse-beach/
├── .github/
│   └── workflows/
│       ├── ci-cd.yml              # Main CI/CD pipeline (lint, test, build, push)
│       └── security-scan.yml      # Dependency vulnerability scanning
│
├── configs/
│   ├── mosquitto.conf             # MQTT broker configuration
│   ├── passwd                     # MQTT credentials (gitignored)
│   └── registry.json              # Sensor metadata registry
│
├── data/                          # Runtime data (Docker volume mount)
│   ├── incoming/                  # MQTT images queue (temp)
│   ├── archive/                   # Archived images (YYYY/MM/DD/)
│   │   └── 2025/12/22/           # Daily subdirectories
│   ├── sensor_log/                # Long-term sensor JSONL files
│   ├── www/                       # Web-served content
│   │   └── timelapses/           # Generated MP4/GIF files
│   ├── status.json                # Live sensor snapshot
│   ├── stats_24h.json             # 24-hour min/max stats
│   ├── history_cache.json         # Sensor history (survives restarts)
│   └── riddle_state.json          # Daily riddle continuity
│
├── scripts/                       # Python application code
│   ├── entrypoint.sh              # Docker entrypoint (starts all services)
│   │
│   │── # === Core Services (run as daemons) ===
│   ├── ingestion.py               # MQTT → incoming/ (image receiver)
│   ├── curator.py                 # incoming/ → archive/ (quality filter)
│   ├── status_daemon.py           # MQTT → status.json (sensor aggregator)
│   ├── scheduler.py               # Cron-like job scheduler
│   ├── web_server.py              # HTTP server for timelapses (:8080)
│   │
│   │── # === Email Generation ===
│   ├── publisher.py               # Main email builder and sender
│   ├── narrator.py                # Gemini AI narrative generation
│   ├── weather_service.py         # OpenWeatherMap integration
│   ├── coast_sky_service.py       # NOAA tides + astronomy events
│   ├── weekly_digest.py           # Weekly stats aggregation
│   ├── stats.py                   # 24-hour statistics helpers
│   │
│   │── # === Media Generation ===
│   ├── timelapse.py               # Daily/weekly GIF generation
│   ├── extended_timelapse.py      # Monthly/yearly MP4 generation
│   ├── golden_hour.py             # Optimal photo timing calculator
│   │
│   │── # === Remote Node Scripts (Greenhouse Pi) ===
│   ├── camera_mqtt_bridge.py      # HA camera → MQTT publisher
│   ├── ha_sensor_bridge.py        # HA sensors → MQTT publisher
│   └── gateway_nat_setup.sh       # Network routing helper
│
├── tests/                         # Pytest test suite (109 tests)
│   ├── test_publisher.py
│   ├── test_narrator.py
│   ├── test_timelapse.py
│   └── ...
│
├── esphome/                       # ESPHome configs for satellite sensors
│   └── satellite-sensor.yaml
│
├── docker-compose.yml             # Production stack definition
├── Dockerfile                     # Multi-stage build (test + production)
├── requirements.txt               # Python dependencies
│
└── docs/                          # Additional documentation
    ├── ARCHITECTURE.md            # (this file)
    ├── CURRENT_STATE.md           # Live system status
    ├── INSTALLATION_GUIDE.md      # Deployment instructions
    └── ...
```

---

## 3. Key Components

### 3.1 Docker Services

| Container | Image | Purpose |
|-----------|-------|---------|
| `greenhouse-mosquitto` | `eclipse-mosquitto:2` | MQTT message broker |
| `greenhouse-storyteller` | `name/greenhouse-storyteller` | Main application (5 Python processes) |

### 3.2 Storyteller Processes

The `greenhouse-storyteller` container runs 5 concurrent processes via `entrypoint.sh`:

| Process | File | Purpose | Trigger |
|---------|------|---------|---------|
| **Ingestion** | `ingestion.py` | Receives MQTT images, saves to `incoming/` | MQTT subscription |
| **Curator** | `curator.py` | Quality-filters images, moves to `archive/` | 10-second polling |
| **Status Daemon** | `status_daemon.py` | Aggregates sensor MQTT → `status.json` | MQTT subscription |
| **Scheduler** | `scheduler.py` | Triggers daily email, timelapses | Cron-like (7 AM) |
| **Web Server** | `web_server.py` | Serves timelapse files on :8080 | HTTP requests |

### 3.3 Email Generation Pipeline

```
scheduler.py (07:00)
       │
       ▼
publisher.py ─────────────────────────────────────────────┐
       │                                                   │
       ├──▶ load_latest_sensor_snapshot()                 │
       │         └── reads status.json                    │
       │                                                   │
       ├──▶ narrator.generate_update(sensor_data)         │
       │         ├── weather_service.get_forecast()       │
       │         ├── coast_sky_service.get_summary()      │
       │         └── Gemini API → subject, headline, body │
       │                                                   │
       ├──▶ timelapse.create_daily_timelapse()            │
       │         └── archive/YYYY/MM/DD/*.jpg → GIF       │
       │                                                   │
       ├──▶ build_email() → HTML with embedded image      │
       │                                                   │
       └──▶ send_email() → Gmail SMTP                     │
```

### 3.4 External Integrations

| Service | Purpose | Rate Limit |
|---------|---------|------------|
| **Google Gemini** | AI narrative generation | ~60 RPM |
| **OpenWeatherMap** | Weather forecast, sunrise/sunset | 1000/day |
| **NOAA CO-OPS** | Tide predictions (Jennette's Pier) | Unlimited |
| **Gmail SMTP** | Email delivery | 500/day |

---

## 4. Data Flow

### 4.1 Image Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Home Assistant │     │  camera_mqtt_   │     │    Mosquitto    │
│  Camera Entity  │────▶│  bridge.py      │────▶│    (MQTT)       │
│  (Greenhouse Pi)│     │  (30 min)       │     │    :1883        │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        Topic: greenhouse/camera/image   │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    archive/     │     │    curator.py   │     │  ingestion.py   │
│  YYYY/MM/DD/    │◀────│  (quality gate) │◀────│  (MQTT → disk)  │
│    *.jpg        │     │  brightness>10  │     │  incoming/*.jpg │
└────────┬────────┘     └─────────────────┘     └─────────────────┘
         │
         │  Daily @ 07:00
         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  timelapse.py   │     │   Email with    │     │   Recipients    │
│  → GIF (60fps)  │────▶│   embedded GIF  │────▶│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 4.2 Sensor Pipeline

```
┌─────────────────┐     ┌─────────────────┐
│  Home Assistant │     │  ha_sensor_     │     Topic: greenhouse/interior/sensor/temp/state
│  Sensor Entities│────▶│  bridge.py      │────▶ greenhouse/interior/sensor/humidity/state
│  (Greenhouse Pi)│     │  (5 min)        │     greenhouse/exterior/sensor/temp/state
└─────────────────┘     └─────────────────┘     ...
                                                         │
┌─────────────────┐     ┌─────────────────┐              │
│  ESPHome        │     │  Native MQTT    │              │
│  Satellite      │────▶│  (deep sleep)   │──────────────┤
│  (FireBeetle)   │     │                 │              │
└─────────────────┘     └─────────────────┘              │
                                                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        status_daemon.py                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  latest_values  │  │  history (24h)  │  │  sensor_log/    │  │
│  │  (in-memory)    │  │  (in-memory)    │  │  (monthly JSONL)│  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────┘  │
│           │                    │                                │
│           ▼                    ▼                                │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │  status.json    │  │  stats_24h.json │                       │
│  │  (live values)  │  │  (min/max/avg)  │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        publisher.py                             │
│                                                                 │
│  sensor_data + weather + tides + AI narrative → HTML email      │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 MQTT Topic Schema

```
greenhouse/
├── camera/
│   └── image                    # Binary JPEG payload (~80KB)
├── interior/
│   └── sensor/
│       ├── temp/state           # "68.5" (°F)
│       └── humidity/state       # "72.3" (%)
├── exterior/
│   └── sensor/
│       ├── temp/state
│       ├── humidity/state
│       └── pressure/state       # "15.02" (inHg)
└── satellite-2/
    └── sensor/
        ├── temperature/state
        ├── humidity/state
        ├── pressure/state
        └── battery/state        # "4.02" (V)
```

---

## 5. Scheduled Jobs

| Job | Schedule | Function |
|-----|----------|----------|
| **Daily Email** | 07:00 | `publisher.run_once()` |
| **Golden Hour Capture** | ~15:45 (seasonal) | Camera trigger |
| **Monthly Timelapse** | 08:00 on 1st | `extended_timelapse.create_monthly_timelapse()` |
| **Yearly Timelapse** | 09:00 on Jan 1 | `extended_timelapse.create_yearly_timelapse()` |

---

## 6. Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `MQTT_HOST` | Broker hostname | `mosquitto` |
| `MQTT_PORT` | Broker port | `1883` |
| `MQTT_USERNAME` | Auth username | — |
| `MQTT_PASSWORD` | Auth password | — |
| `GEMINI_API_KEY` | Google AI key | — |
| `OPENWEATHER_API_KEY` | Weather API | — |
| `SMTP_SERVER` | Email server | `smtp.gmail.com` |
| `SMTP_USER` | Email username | — |
| `SMTP_PASSWORD` | App password | — |
| `SMTP_TO` | Recipients (comma-separated) | — |
| `TZ` | Timezone | `America/New_York` |

---

## 7. Deployment

### Quick Start
```bash
# Clone and configure
git clone https://github.com/name/greenhouse-beach.git
cp .env.example .env
# Edit .env with your credentials

# Build and run
docker compose build
docker compose up -d

# Check logs
docker compose logs -f
```

### CI/CD Pipeline
```
Push to main → GitHub Actions → Lint/Test → Build Docker → Push to Docker Hub
```

See `DEPLOYMENT.md` and `INSTALLATION_GUIDE.md` for detailed instructions.

---

## 8. Key Design Decisions

1. **MQTT over HTTP**: Lightweight, fire-and-forget messaging suited for IoT devices
2. **File-based state**: `status.json` simplifies debugging and survives restarts
3. **Separate archive structure**: `YYYY/MM/DD/` enables efficient timelapse queries
4. **Multi-process entrypoint**: Simpler than async, matches Docker restart semantics
5. **AI narrative**: Gemini transforms raw data into engaging, context-aware prose
6. **Weekly Edition**: Sunday email merges daily + weekly content (not separate emails)

---

*Last updated: Dec 22, 2025*
