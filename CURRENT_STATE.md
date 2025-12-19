# Project Chlorophyll: Current System State
**Status:** Pre-Deployment / Ready for Installation
**Last Updated:** Dec 19, 2025

## Active Architecture
* **Hardware:** Raspberry Pi 5 (running Bookworm Lite).
* **Storage:** SD Card (NVMe migration pending).
* **Services (Docker):**
    1.  `mosquitto` (Port 1883) - MQTT broker accepting external connections.
    2.  `storyteller` (Python container running 4 parallel processes).

## Running Processes (Storyteller Container)
1.  `ingestion.py` - Listens for images on `greenhouse/+/image`
2.  `curator.py` - Processes and archives incoming images
3.  `scheduler.py` - Triggers Daily Dispatch at 07:00 local time
4.  `status_daemon.py` - Maintains `status.json` and `stats_24h.json` from MQTT sensor data

## Critical Configuration Overrides
1.  **Hardware Bypass:** Camera device mapping is **COMMENTED OUT** - images come via MQTT from Greenhouse Pi.
2.  **MQTT Patch:** Uses `mqtt.CallbackAPIVersion.VERSION2` for Paho 2.x compatibility.
3.  **Model Selection:** `gemini-2.5-flash` primary, `gemini-flash-latest` fallback.
4.  **Weather API:** OpenWeatherMap **One Call 3.0** (`/data/3.0/onecall`).
5.  **Temp Conversion:** Satellite temps converted from °C to °F in `publisher.py`.

## Verification Status
* [x] **MQTT Ingestion:** Active. Receiving satellite sensor data.
* [x] **Satellite Sensor:** FireBeetle ESP32-E publishing every 15 min.
* [x] **Status Daemon:** Writing sensor snapshots to `status.json`.
* [x] **24h Stats:** Tracking min/max for temp and humidity.
* [x] **Gemini Narrative:** Authenticated and generating daily updates.
* [x] **Weather Integration:** One Call 3.0 working with valid API key.
* [x] **Email Publishing:** SMTP working via Gmail App Password.
* [x] **Scheduler:** Firing Daily Dispatch at 07:00 EST.

## Deployment Preparation Status
* [x] **DEPLOYMENT.md:** Architecture and installation guide created.
* [x] **gateway_nat_setup.sh:** NAT/iptables script for Greenhouse Pi.
* [x] **camera_mqtt_bridge.py:** Captures HA camera → MQTT.
* [x] **camera-mqtt-bridge.service:** Systemd unit file.
* [x] **mosquitto.conf:** Updated to accept external connections.
* [x] **registry.json:** Updated with production network topology.

## Pending for On-Site Installation
1.  **Set Storyteller static IP** on beachFi network.
2.  **Run gateway_nat_setup.sh** on Greenhouse Pi with Storyteller IP.
3.  **Deploy camera_mqtt_bridge.py** as systemd service on Greenhouse Pi.
4.  **Flash satellite sensor** with GREENHOUSE_IOT WiFi credentials.
5.  **Verify end-to-end** data flow and email delivery.