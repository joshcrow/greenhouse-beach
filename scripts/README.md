# Scripts - Core Application Logic

> This directory contains the Python modules that power the Greenhouse Gazette system.

---

## Overview

The scripts are organized into three categories:

| Category | Modules | Purpose |
|----------|---------|---------|
| **Daemon Services** | `ingestion`, `curator`, `status_daemon`, `scheduler`, `web_server` | Long-running processes started by `entrypoint.sh` |
| **Email Generation** | `publisher`, `narrator`, `weather_service`, `coast_sky_service`, `weekly_digest`, `stats` | Daily email composition pipeline |
| **Media Generation** | `timelapse`, `extended_timelapse`, `golden_hour` | Image processing and video creation |
| **Remote Node** | `camera_mqtt_bridge`, `ha_sensor_bridge` | Run on remote Pi, not in Docker |

---

## Daemon Services

### `ingestion.py`

**Responsibility:** Receives images from MQTT and saves them to the incoming queue.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `on_message()` | MQTT callback that writes payload to `/app/data/incoming/` |
| `generate_filename()` | Creates deterministic filename: `img_{device}_{YYYYMMDD_HHMMSS}.jpg` |
| `run_client_loop()` | Connects to broker and runs `loop_forever()` |

**Dependencies:**
- `paho-mqtt` - MQTT client library
- Environment: `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`

**Edge Cases & Error Handling:**
- **Atomic writes**: Uses `.tmp` suffix + `os.rename()` to prevent curator from reading partial files
- **Reconnection**: Outer `while True` loop with 5-second backoff on connection failure
- **Auth failure**: Logs `rc` code but does not expose credentials

**Security Notes:**
- Credentials read from environment, never logged
- Subscribes only to `greenhouse/+/image` topic filter

---

### `curator.py`

**Responsibility:** Quality-gates incoming images and archives valid ones.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `process_file()` | Reads image, computes brightness, routes to archive or reject |
| `archive_path_for()` | Generates `YYYY/MM/DD/` directory structure |
| `list_candidate_files()` | Filters for `.jpg/.jpeg/.png`, excludes `.tmp` files |

**Dependencies:**
- `opencv-python-headless` - Image loading and grayscale conversion
- Reads from: `/app/data/incoming/`
- Writes to: `/app/data/archive/YYYY/MM/DD/`

**Brightness Thresholds:**
| Threshold | Value | Action |
|-----------|-------|--------|
| `BRIGHTNESS_MIN_NIGHT` | 10 | Archive to `_night/` subdirectory |
| `BRIGHTNESS_MIN_DIM` | 30 | Log warning, archive anyway |
| `BRIGHTNESS_MAX_OVEREXPOSED` | 250 | Delete (rejected) |

**Edge Cases & Error Handling:**
- **Corrupt images**: `cv2.imread()` returns `None` → delete file
- **Processing errors**: Delete file to prevent infinite retry loop
- **Race condition**: Skips `.tmp` files still being written by ingestion

---

### `status_daemon.py`

**Responsibility:** Aggregates sensor MQTT messages into a live snapshot and 24-hour statistics.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `on_message()` | Parses MQTT payload, validates range, updates in-memory state |
| `_validate_numeric()` | Enforces temp (-10°F to 130°F) and humidity (0-100%) bounds |
| `_is_spike()` | Detects sudden value jumps (>20°F temp or >30% humidity in 10 min) |
| `_save_history_cache()` | Persists 24h history to disk for crash recovery |
| `_write_sensor_log()` | Appends readings to monthly JSONL for long-term analysis |

**Dependencies:**
- `paho-mqtt` - MQTT subscription
- Writes to: `status.json`, `stats_24h.json`, `history_cache.json`, `sensor_log/YYYY-MM.jsonl`

**Data Validation (REQ-3.1):**
```
Temperature:  -10°F ≤ value ≤ 130°F  (out-of-bounds → rejected)
Humidity:       0%  ≤ value ≤ 100%   (out-of-bounds → rejected)
Spike:        >20°F or >30% change in 10 minutes → logged, not ingested
```

**Edge Cases & Error Handling:**
- **Satellite temp conversion**: Auto-converts C→F for `satellite-*` device IDs
- **Buffer overflow protection**: `MAX_SENSOR_LOG_BUFFER=1000` evicts oldest on overflow
- **Atomic writes**: Uses `tmp` + `os.replace()` + `os.fsync()` for crash safety
- **History persistence**: Loads cache on startup to survive container restarts

**Security Notes:**
- No sensitive data in MQTT payloads (numeric values only)
- Topic parsing is strict: must match `greenhouse/{device}/sensor/{key}/state`

---

### `scheduler.py`

**Responsibility:** Cron-like job scheduler for daily emails and timelapse generation.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `safe_daily_dispatch()` | Calls `publisher.run_once()` with error handling |
| `generate_monthly_timelapse()` | Creates MP4 on 1st of month |
| `generate_yearly_timelapse()` | Creates MP4 on January 1st |
| `main()` | Registers jobs and runs `schedule.run_pending()` loop |

**Scheduled Jobs:**
| Job | Time | Condition |
|-----|------|-----------|
| Daily Email | 07:00 | Every day (Sunday = Weekly Edition) |
| Golden Hour | ~15:45 | Seasonal, calculated by `golden_hour.py` |
| Monthly Timelapse | 08:00 | Only on day 1 |
| Yearly Timelapse | 09:00 | Only on Jan 1 |

**Dependencies:**
- `schedule` - Job scheduling library
- Imports: `publisher`, `weekly_digest`, `golden_hour`, `extended_timelapse`

**Edge Cases:**
- **Weekly Edition**: Detected via `datetime.now().weekday() == 6` (Sunday)
- **Job failures**: Caught and logged, does not crash scheduler loop

---

### `web_server.py`

**Responsibility:** Serves static files (timelapses) over HTTP on port 8080.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `main()` | Starts `http.server` on `:8080` serving `/app/data/www/` |

**Dependencies:**
- Python stdlib `http.server`
- Serves: `/app/data/www/timelapses/*.mp4`

**Security Notes:**
- Intended for internal/Tailscale access only
- No authentication (assumes network-level security)

---

### `email_preview.py`

**Responsibility:** Hot-reload preview server for email templates during development.

**Usage:**
```bash
# Via Docker (recommended)
docker compose --profile dev up email-preview

# Direct (local dev)
python scripts/email_preview.py
```

Then visit: **http://localhost:8081/**

**Preview Scenarios:**
| Scenario | URL | Description |
|----------|-----|-------------|
| Normal | `/preview?scenario=normal` | Clear day, all systems working |
| Alerts | `/preview?scenario=alerts` | Frost risk, low battery, high wind |
| Stale | `/preview?scenario=stale` | Missing sensor data |

**Hot Reload:**
- Edit any file in `templates/` and refresh browser
- No server restart needed - templates reload on every request

**Dependencies:**
- Python stdlib `http.server`
- Jinja2 templates in `templates/`

**Port:** 8081 (configurable via `PREVIEW_PORT` env var)

---

## Sensor Remapping (Critical!)

> ⚠️ **Important:** Physical sensor names don't match their logical roles due to hardware history.

### The Mapping

| Raw Key (MQTT) | Logical Role | Physical Location |
|----------------|--------------|-------------------|
| `exterior_temp` | `interior_temp` | **Inside** greenhouse |
| `exterior_humidity` | `interior_humidity` | **Inside** greenhouse |
| `satellite-2_temperature` | `exterior_temp` | **Outside** (weather station) |
| `satellite-2_humidity` | `exterior_humidity` | **Outside** (weather station) |
| `interior_*` | *(suppressed)* | Broken hardware, ignore |

### Why?

The original interior sensor failed and was replaced. Rather than re-flash the ESPHome config on the replacement device, we kept the existing `exterior_*` topic names. The "satellite-2" device is the outdoor weather station.

### Where Remapping Happens

1. **`publisher.py`** - `build_email()` function remaps before display
2. **`app/models.py`** - `SensorSnapshot.from_status_dict()` handles remapping
3. **`status_daemon.py`** - Stores raw MQTT keys, no remapping

### Code Reference

```python
# In publisher.py build_email():
sensor_mapping = [
    ("exterior_temp", "interior_temp"),
    ("exterior_humidity", "interior_humidity"),
    ("satellite-2_temperature", "exterior_temp"),
    ("satellite-2_humidity", "exterior_humidity"),
]
```

---

## Email Generation Pipeline

### `publisher.py`

**Responsibility:** Orchestrates email composition, from sensor data to SMTP delivery.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `build_email()` | Assembles HTML email with embedded timelapse GIF |
| `load_latest_sensor_snapshot()` | Reads `status.json` (HTTP fallback to local file) |
| `find_latest_image()` | Glob searches archive for most recent JPG |
| `run_once()` | Main entry point: load data → generate narrative → build email → send |

**Email Composition Flow:**
```
load_latest_sensor_snapshot()
        │
        ▼
narrator.generate_update(sensor_data)
        │
        ▼
timelapse.create_daily_timelapse()  ──or──  find_latest_image() [fallback]
        │
        ▼
build_email() → HTML with CID-embedded image
        │
        ▼
smtplib.SMTP_SSL() → send
```

**Dependencies:**
- Environment: `SMTP_SERVER`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TO`, `SMTP_FROM`
- Imports: `narrator`, `timelapse`, `stats`, `weekly_digest`

**Edge Cases & Error Handling:**
- **No timelapse**: Falls back to latest static JPEG
- **No images at all**: Sends email without hero image
- **Narrator failure**: Uses fallback subject/headline/body
- **SMTP failure**: Logged, exception propagates to scheduler

**Security Notes:**
- SMTP credentials from environment, never logged
- Email addresses not hardcoded in source

---

### `narrator.py`

**Responsibility:** Generates AI-powered narrative content via Google Gemini API.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `generate_update()` | Main entry: sanitize → augment with weather → prompt → parse response |
| `sanitize_data()` | Clamps sensor values to safe ranges per REQ-3.1 |
| `build_prompt()` | Constructs system prompt with persona and rules |
| `_get_client()` | Lazy-initializes Gemini client from `GEMINI_API_KEY` |

**Data Sanitization (REQ-3.1):**
```python
Temperature:  -10°F to 130°F  → out-of-bounds replaced with None
Humidity:       0% to 100%    → out-of-bounds replaced with None
```

**Prompt Engineering:**
- Enforces "no emoji" rule
- Instructs AI to use `<b>bold</b>` for alerts
- Prevents hallucination of Coast & Sky data (only use if present)
- Strict output format: `SUBJECT:`, `HEADLINE:`, `BODY:`

**Dependencies:**
- `google-genai` - Gemini API client
- Environment: `GEMINI_API_KEY`, `GEMINI_MODEL` (default: `gemini-3-flash-preview`)
- Imports: `weather_service`, `coast_sky_service`

**Edge Cases & Error Handling:**
- **Missing API key**: Raises `ValueError` (fail-fast)
- **Parse failure**: Falls back to partial extraction or hardcoded defaults
- **Rate limiting**: Caught as exception, logged

**Security Notes:**
- API key read from environment, never logged or included in prompts
- Sensor data sanitized before AI ingestion (prevents prompt injection via malformed data)

---

### `weather_service.py`

**Responsibility:** Fetches current weather and forecast from OpenWeatherMap API.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `get_current_weather()` | Returns dict with temp, humidity, wind, moon phase, sunrise/sunset |
| `_moon_phase_icon()` | Maps 0-1 phase value to Unicode moon emoji |
| `_wind_direction()` | Converts degrees to compass direction (N, NE, E, ...) |

**Returns:** (on success)
```python
{
    "outdoor_temp": 45,
    "condition": "Clouds",
    "humidity_out": 72,
    "high_temp": 52,
    "low_temp": 38,
    "wind_mph": 12,
    "wind_direction": "NW",
    "sunrise": "7:02 AM",
    "sunset": "5:14 PM",
    "moon_phase": 0.75,
    "moon_icon": "🌗",
    ...
}
```

**Dependencies:**
- `requests` - HTTP client
- Environment: `OPENWEATHER_API_KEY`, `LAT`, `LON`, `TZ`

**Edge Cases & Error Handling:**
- **Missing config**: Returns empty dict (never raises)
- **API error/timeout**: Returns empty dict, logs error
- **All values rounded**: Integers for cleaner display

**Security Notes:**
- API key redacted in log output: `appid=***REDACTED***`
- Never exposes coordinates in error messages

---

### `coast_sky_service.py`

**Responsibility:** Fetches tide predictions (NOAA) and astronomical events (meteor showers, moon phases).

**Key Functions:**
| Function | Description |
|----------|-------------|
| `get_coast_sky_summary()` | Main entry: returns tide + sky data for narrative |
| `_fetch_noaa_tides()` | Queries NOAA CO-OPS API for high/low tide times |
| `_get_sky_summary()` | Checks for meteor showers and named moon events |

**Returns:** (example)
```python
{
    "tide_summary": {
        "high_tides": [...],
        "low_tides": [...],
        "is_king_tide_window": False,
    },
    "sky_summary": {
        "meteor_shower_name": "Geminids",
        "is_peak_window": True,
    },
    "moon_event_summary": {
        "full_moon_name": "Cold Moon",
    }
}
```

**Dependencies:**
- `requests` - HTTP client
- NOAA CO-OPS API (no key required)
- Hardcoded data: Meteor shower dates, named full moons

**Caching:**
- Results cached to `/app/data/calendars/coast_sky_cache.json`
- Cache expires daily

---

### `stats.py`

**Responsibility:** Reads 24-hour min/max statistics for email vitals display.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `get_24h_stats()` | Loads and returns metrics from `stats_24h.json` |

**Dependencies:**
- Reads: `/app/data/stats_24h.json` (written by `status_daemon.py`)

**Edge Cases:**
- **File missing**: Returns empty dict, email shows "N/A"
- **Invalid JSON**: Returns empty dict, logs warning

---

### `weekly_digest.py`

**Responsibility:** Accumulates daily snapshots for weekly summary statistics.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `record_daily_snapshot()` | Appends today's stats to weekly accumulator |
| `compute_weekly_summary()` | Aggregates min/max/avg across 7 days |
| `load_weekly_stats()` / `save_weekly_stats()` | Persistence helpers |

**Dependencies:**
- Reads: `stats_24h.json`
- Writes: `stats_weekly.json`

**Edge Cases:**
- **Rolling window**: Keeps only last 7 days, auto-prunes older entries

---

## Media Generation

### `timelapse.py`

**Responsibility:** Creates animated GIF timelapses for daily/weekly emails.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `create_daily_timelapse()` | Yesterday's daylight images → 60-frame GIF |
| `create_weekly_timelapse()` | Past 7 days → 100-frame GIF |
| `get_yesterday_images()` | Filters archive for daylight hours only |
| `create_timelapse_gif()` | Core GIF assembly with Pillow |

**Daylight Filtering:**
- Uses `get_sunrise_sunset()` from OpenWeather API
- Fallback: 7 AM to 6 PM if API unavailable
- Extracts timestamp from filename: `img_camera_YYYYMMDD_HHMMSS.jpg`

**GIF Parameters:**
| Parameter | Daily | Weekly |
|-----------|-------|--------|
| Max frames | 60 | 100 |
| Frame duration | 100ms | 100ms |
| Max width | 600px | 600px |
| Colors | 128 | 256 |

**Dependencies:**
- `Pillow` - Image processing and GIF creation
- `requests` - OpenWeather API for sunrise/sunset
- Reads: `/app/data/archive/YYYY/MM/DD/*.jpg`

**Edge Cases & Error Handling:**
- **No images**: Returns `None`, publisher falls back to static image
- **< 2 valid frames**: Returns `None`
- **Corrupt images**: Skipped with logged warning

---

### `extended_timelapse.py`

**Responsibility:** Creates high-quality MP4 timelapses for monthly/yearly summaries.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `create_monthly_timelapse()` | Previous month → 500-frame MP4 |
| `create_yearly_timelapse()` | Previous year → 4000-frame MP4 |
| `prepare_frames()` | Resizes images and copies to temp dir with sequential naming |
| `create_mp4_timelapse()` | Invokes FFmpeg to encode video |

**Video Parameters:**
| Parameter | Monthly | Yearly |
|-----------|---------|--------|
| Target frames | 500 | 4000 |
| FPS | 24 | 30 |
| Resolution | 1280px wide | 1920px wide |
| Codec | H.264 | H.264 |

**Dependencies:**
- `Pillow` - Image resizing
- `ffmpeg` - Video encoding (system binary)
- Writes: `/app/data/www/timelapses/monthly_YYYY_MM.mp4`

**Edge Cases:**
- **FFmpeg missing**: Logs error, returns `None`
- **< 10 images**: Skips generation

---

### `golden_hour.py`

**Responsibility:** Calculates optimal photo capture time based on sunset.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `get_sunset_time()` | Fetches today's sunset from OpenWeather |
| `get_seasonal_golden_hour()` | Returns capture time string for scheduler |

**Dependencies:**
- `requests` - OpenWeather API
- Environment: `OPENWEATHER_API_KEY`, `LAT`, `LON`

---

## Remote Node Scripts

> These run on the Greenhouse Pi, not in Docker.

### `camera_mqtt_bridge.py`

**Responsibility:** Captures camera snapshots and publishes to MQTT.

**Key Functions:**
| Function | Description |
|----------|-------------|
| `capture_from_ha()` | Fetches snapshot from Home Assistant camera entity |
| `capture_from_libcamera()` | Fallback: direct `libcamera-still` capture |
| `publish_to_mqtt()` | Publishes JPEG bytes to MQTT broker |
| `run_daemon()` | Continuous capture loop with configurable interval |

**Dependencies:**
- `paho-mqtt` - MQTT client (use legacy API for Paho 1.x compatibility)
- `requests` - Home Assistant API
- Environment: `HA_URL`, `HA_TOKEN`, `HA_CAMERA_ENTITY`, `MQTT_HOST`, etc.

**Edge Cases:**
- **HA unavailable**: Falls back to libcamera if `USE_LIBCAMERA_FALLBACK=True`
- **MQTT publish failure**: Logs error, continues to next interval
- **Uses `loop_start()`**: Required for non-blocking publish

**Security Notes:**
- HA token from environment, never logged
- MQTT credentials from environment

---

### `ha_sensor_bridge.py`

**Responsibility:** Bridges Home Assistant sensor entities to MQTT.

**Dependencies:**
- Environment: `HA_URL`, `HA_TOKEN`, sensor entity configuration
- Publishes to: `greenhouse/{zone}/sensor/{type}/state`

---

## Configuration Reference

### Required Environment Variables

| Variable | Used By | Purpose |
|----------|---------|---------|
| `MQTT_HOST` | ingestion, status_daemon | Broker hostname |
| `MQTT_PORT` | ingestion, status_daemon | Broker port (default: 1883) |
| `MQTT_USERNAME` | ingestion, status_daemon | Auth username |
| `MQTT_PASSWORD` | ingestion, status_daemon | Auth password |
| `GEMINI_API_KEY` | narrator | Google AI API key |
| `OPENWEATHER_API_KEY` | weather_service, timelapse | Weather API key |
| `LAT`, `LON` | weather_service, timelapse, golden_hour | Location coordinates |
| `SMTP_SERVER` | publisher | Email server (default: smtp.gmail.com) |
| `SMTP_USER` | publisher | Email username |
| `SMTP_PASSWORD` | publisher | Email app password |
| `SMTP_TO` | publisher | Recipients (comma-separated) |
| `TZ` | weather_service | Timezone (default: America/New_York) |

### Optional Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GEMINI_MODEL` | gemini-3-flash-preview | AI model name |
| `WEATHER_UNITS` | imperial | API units (imperial/metric) |
| `STATUS_WRITE_INTERVAL` | 60 | Seconds between status.json writes |
| `TEMP_MIN_F` / `TEMP_MAX_F` | -10 / 130 | Sensor validation bounds |

---

## Security Considerations

1. **Credentials**: All secrets loaded from environment variables, never hardcoded
2. **Logging**: API keys redacted in all log output
3. **Data Validation**: Sensor values sanitized before AI ingestion (prevents prompt injection)
4. **Atomic Writes**: All file operations use tmp+rename pattern to prevent corruption
5. **Network**: Web server intended for internal/VPN access only (no auth)
6. **MQTT Topics**: Strict parsing prevents topic injection attacks

---

*Last updated: Jan 5, 2026*
