# Project Chlorophyll: Current System State
**Status:** MVP / Staging (SD Card)
**Last Updated:** Dec 1, 2025

## Active Architecture
* **Hardware:** Raspberry Pi 5 (running Bookworm Lite).
* **Storage:** Currently running on SD Card. NVMe drive arriving Wednesday (Migration pending).
* **Services (Docker):**
    1.  `mosquitto` (Port 1883).
    2.  `storyteller` (Python container running 3 parallel processes).

## Critical Configuration Overrides
1.  **Hardware Bypass:** The `devices: /dev/video0` mapping in `docker-compose.yml` is **COMMENTED OUT** because no camera is attached yet.
2.  **MQTT Patch:** `scripts/ingestion.py` uses `mqtt.CallbackAPIVersion.VERSION2` to fix Paho deprecation warnings.
3.  **Model Selection:** `scripts/narrator.py` is hardcoded to `gemini-2.5-flash` (fallback: `gemini-flash-latest`) to match available API models.
4.  **Process Manager:** The `entrypoint.sh` launches three processes: `ingestion.py`, `curator.py`, and `scheduler.py`.
5.  **Weather API:** `scripts/weather_service.py` targets OpenWeatherMap **One Call 3.0** (`/data/3.0/onecall`) due to API key incompatibility with v2.5.

## Current Verification Status
* [x] **MQTT Ingestion:** Active. Tested with fake data.
* [x] **Curator Logic:** Active. Filters low luminance and corrupt files.
* [x] **Gemini Narrative:** Authenticated. Generating text with sensor data.
* [x] **Weather Integration:** Script updated for One Call 3.0. (Requires valid subscription key in .env).
* [x] **Email Publishing:** SMTP authenticated (App Password) and successfully delivered HTML email with image.
* [x] **Scheduler:** Verified running (PID active) and awaiting 07:00 trigger.

## Next Steps
1.  **Burn-In Test:** Run continuously for 48h to check thermal stability and memory leaks.
2.  **Hardware Migration:** Clone SD card to NVMe drive (Wednesday).
3.  **Camera Activation:** Uncomment video device mapping once hardware is installed.