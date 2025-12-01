# Project Chlorophyll: Current System State
**Status:** MVP / Staging (SD Card)
**Last Updated:** [Current Date]

## Active Architecture
* **Hardware:** Raspberry Pi 5 (running Bookworm Lite).
* **Storage:** Currently running on SD Card. NVMe drive arriving Wednesday (Migration pending).
* **Services:**
    1.  `mosquitto` (Port 1883).
    2.  `storyteller` (Python container).

## Critical Configuration Overrides
1.  **Hardware Bypass:** The `devices: /dev/video0` mapping in `docker-compose.yml` is **COMMENTED OUT** because no camera is attached yet.
2.  **MQTT Patch:** `scripts/ingestion.py` uses `mqtt.CallbackAPIVersion.VERSION2` to fix Paho deprecation warnings.
3.  **Model Selection:** `scripts/narrator.py` is hardcoded to `gemini-2.5-flash` (fallback: `gemini-flash-latest`) to match available API models.
4.  **Scheduler:** The `entrypoint.sh` launches three processes: `ingestion`, `curator`, and `scheduler`.

## Current Verification Status
* [x] MQTT Ingestion (Tested with fake data).
* [x] Curator Logic (Tested with luminance filters).
* [x] Gemini Narrative (Authenticated and speaking).
* [x] Email Publishing (SMTP authenticated and sending).
* [x] Scheduler (Looping correctly).

## Next Steps
1.  Wait for NVMe Drive.
2.  Perform cloning/migration.
3.  Uncomment video device mapping once camera is attached.