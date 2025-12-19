# Greenhouse Gazette: Deployment Guide

## Target Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      beachFi (Home Network)                      │
│                        192.168.x.0/24                            │
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────────────┐ │
│  │  Storyteller Pi  │              │    Greenhouse Pi         │ │
│  │  (Node B)        │              │    (Node A / Gateway)    │ │
│  │                  │              │                          │ │
│  │  Docker:         │◄─── MQTT ───►│  - Home Assistant        │ │
│  │  - mosquitto     │   (1883)     │  - Camera Stream         │ │
│  │  - storyteller   │              │  - ESPHome               │ │
│  │                  │              │  - hostapd (AP mode)     │ │
│  │  IP: Static      │              │  - NAT Gateway           │ │
│  └──────────────────┘              └───────────┬──────────────┘ │
│                                                │ wlan0 (AP)     │
└────────────────────────────────────────────────┼────────────────┘
                                                 │
                                                 ▼
                              ┌──────────────────────────────────┐
                              │      GREENHOUSE_IOT Network      │
                              │           10.0.0.0/24            │
                              │                                  │
                              │  ┌────────────┐  ┌────────────┐  │
                              │  │ Satellite  │  │ Satellite  │  │
                              │  │ Sensor 1   │  │ Sensor 2   │  │
                              │  │ (ESP32)    │  │ (ESP32)    │  │
                              │  └────────────┘  └────────────┘  │
                              │                                  │
                              │  Gateway: 10.0.0.1 (Greenhouse Pi)│
                              └──────────────────────────────────┘
```

## Data Flow

1. **Satellite Sensors** → MQTT (via NAT) → **mosquitto** on Storyteller
2. **Camera** → HA snapshot → MQTT bridge script → **mosquitto** → ingestion.py
3. **Indoor Sensors** → ESPHome → MQTT → **mosquitto** → status_daemon.py
4. **Weather API** → narrator.py → **Daily Email** @ 7:00 AM

## Pre-Deployment Checklist

### On Your Development Machine (NOW)

- [ ] Run `docker compose build --no-cache` to ensure image is current
- [ ] Test email delivery: `docker exec greenhouse-beach-storyteller-1 python -c "import publisher; publisher.run_once()"`
- [ ] Verify `.env` has correct SMTP credentials
- [ ] Copy project to USB drive or ensure git is up-to-date

### On Storyteller Pi (at Mom's)

1. **Set Static IP** on beachFi network (e.g., 192.168.1.50)
   ```bash
   sudo nmcli con mod "beachFi" ipv4.addresses 192.168.1.50/24
   sudo nmcli con mod "beachFi" ipv4.gateway 192.168.1.1
   sudo nmcli con mod "beachFi" ipv4.method manual
   sudo nmcli con up "beachFi"
   ```

2. **Clone/Copy Project**
   ```bash
   cd /home/joshcrow
   git clone <repo> greenhouse-beach  # or copy from USB
   ```

3. **Configure Environment**
   ```bash
   cd greenhouse-beach
   cp .env.example .env
   nano .env  # Set API keys, SMTP, etc.
   ```

4. **Start Services**
   ```bash
   docker compose up -d
   docker compose logs -f  # Watch for errors
   ```

### On Greenhouse Pi (at Mom's)

1. **Enable IP Forwarding**
   ```bash
   echo 'net.ipv4.ip_forward=1' | sudo tee -a /etc/sysctl.conf
   sudo sysctl -p
   ```

2. **Configure NAT (Port Forward MQTT)**
   ```bash
   # Run the setup script (see scripts/gateway_nat_setup.sh)
   sudo ./scripts/gateway_nat_setup.sh 192.168.1.50
   ```

3. **Install Camera Bridge Script**
   ```bash
   # Copy camera_mqtt_bridge.py to Greenhouse Pi
   # Set up as systemd service
   ```

### On Satellite Sensors (ESPHome)

Update ESPHome YAML to use the NAT gateway IP:
```yaml
mqtt:
  broker: 10.0.0.1  # Greenhouse Pi AP IP (NAT forwards to Storyteller)
  port: 1883
  topic_prefix: greenhouse/satellite-2
```

## Verification Steps (at Mom's)

1. **Test MQTT from Satellite → Storyteller**
   ```bash
   # On Storyteller:
   docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t "greenhouse/#" -v
   # Should see satellite messages arrive
   ```

2. **Test Camera Bridge**
   ```bash
   # On Greenhouse Pi:
   python3 camera_mqtt_bridge.py --test
   # Should publish one image to MQTT
   ```

3. **Test End-to-End Email**
   ```bash
   # On Storyteller:
   docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py
   # Should receive test email
   ```

## File Inventory for Deployment

```
greenhouse-beach/
├── .env                    # ⚠️ Contains secrets - configure on-site
├── docker-compose.yml      # Ready
├── Dockerfile              # Ready
├── configs/
│   ├── mosquitto.conf      # Updated for external access
│   └── registry.json       # Updated with production devices
├── scripts/
│   ├── gateway_nat_setup.sh      # NEW: Run on Greenhouse Pi
│   └── camera_mqtt_bridge.py     # NEW: Run on Greenhouse Pi
└── data/                   # Will be created by services
```

## Troubleshooting

### Satellites can't connect to MQTT
- Verify NAT is configured: `sudo iptables -t nat -L -n`
- Check Greenhouse Pi is forwarding: `cat /proc/sys/net/ipv4/ip_forward`
- Test from satellite network: `nc -zv 10.0.0.1 1883`

### No camera images arriving
- Check camera bridge logs: `journalctl -u camera-mqtt-bridge -f`
- Verify HA camera entity exists: `curl http://localhost:8123/api/camera_proxy/camera.greenhouse`
- Test MQTT publish: `mosquitto_pub -h 192.168.1.50 -t test -m "hello"`

### Email not sending at 7AM
- Check scheduler is running: `docker exec greenhouse-beach-storyteller-1 ps aux | grep scheduler`
- Check timezone: `docker exec greenhouse-beach-storyteller-1 date`
- Manual test: `docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py`
