# GAME DAY INSTALLATION GUIDE

**Purpose:** Step-by-step commands for on-site deployment at Mom's house.  
**Time Required:** 30-45 minutes  
**Last Verified:** December 19, 2025

---

## PREREQUISITES

### Hardware Checklist
- [ ] Storyteller Pi 5 + power supply
- [ ] Satellite sensor (FireBeetle) + charged battery (>3.7V)
- [ ] Laptop with Tailscale installed

### Software Versions
| Component | Required Version |
|-----------|------------------|
| Raspberry Pi OS | Debian 12 (Bookworm) 64-bit |
| Docker | 24.0+ |
| Docker Compose | V2 (plugin) |
| Python | 3.11 |
| Tailscale | Latest |

### Environment Variables Required
```
GEMINI_API_KEY=        # Google AI API key
OPENWEATHER_API_KEY=   # OpenWeather One Call 3.0 key
SMTP_USER=             # Gmail address
SMTP_PASSWORD=         # Gmail App Password
MQTT_PASSWORD=         # Generated: openssl rand -base64 24
```

### Network Info (Pre-filled for Mom's)
| Item | Value |
|------|-------|
| WiFi SSID | `beachFi` |
| Storyteller Static IP | `192.168.1.50` |
| Gateway | `192.168.1.1` |
| Storyteller Tailscale | `100.94.172.114` |
| Greenhouse Pi Tailscale | `100.110.161.42` |

---

## PHASE 1: STORYTELLER PI SETUP

### Step 1.1: Connect and Verify
```bash
# SSH via Tailscale (works from anywhere)
ssh joshcrow@100.94.172.114

# Verify WiFi connected to beachFi
nmcli connection show --active
# Expected: beachFi  wifi  wlan0
```

### Step 1.2: Set Static IP
```bash
# Configure static IP
sudo nmcli connection modify "beachFi" \
    ipv4.method manual \
    ipv4.addresses "192.168.1.50/24" \
    ipv4.gateway "192.168.1.1" \
    ipv4.dns "8.8.8.8,8.8.4.4"

# Apply changes
sudo nmcli connection down "beachFi" && sudo nmcli connection up "beachFi"

# Verify (may need to reconnect SSH)
ip addr show wlan0 | grep "inet "
# Expected: inet 192.168.1.50/24
```

### Step 1.3: Start Docker Services
```bash
cd ~/greenhouse-beach

# Pull latest code (if using git)
git pull

# Build and start
docker compose build --no-cache
docker compose up -d

# Verify containers running
docker ps
# Expected: 2 containers (mosquitto, storyteller)
```

### Step 1.4: Verify Storyteller Services
```bash
# Check all 4 processes are running
docker exec greenhouse-beach-storyteller-1 ps aux | grep python
# Expected: ingestion.py, curator.py, scheduler.py, status_daemon.py

# Check MQTT broker accepting connections
docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t "\$SYS/#" -C 1
# Expected: Any system message = broker working
```

---

## PHASE 2: GREENHOUSE PI CONFIGURATION

### Step 2.1: Connect to Greenhouse Pi
```bash
# From your laptop (via Tailscale)
ssh joshcrow@100.110.161.42
```

### Step 2.2: Update Bridge Configs
```bash
# Set Storyteller IP in bridge configs
STORYTELLER_IP="192.168.1.50"

# Update sensor bridge
sudo sed -i "s/MQTT_HOST=.*/MQTT_HOST=$STORYTELLER_IP/" /opt/greenhouse/ha_sensor_bridge.env
echo "MQTT_USERNAME=greenhouse" | sudo tee -a /opt/greenhouse/ha_sensor_bridge.env
echo "MQTT_PASSWORD=YOUR_MQTT_PASSWORD_HERE" | sudo tee -a /opt/greenhouse/ha_sensor_bridge.env

# Update camera bridge
sudo sed -i "s/MQTT_HOST=.*/MQTT_HOST=$STORYTELLER_IP/" /opt/greenhouse/camera_mqtt_bridge.env
echo "MQTT_USERNAME=greenhouse" | sudo tee -a /opt/greenhouse/camera_mqtt_bridge.env
echo "MQTT_PASSWORD=YOUR_MQTT_PASSWORD_HERE" | sudo tee -a /opt/greenhouse/camera_mqtt_bridge.env

# Restart bridge services
sudo systemctl restart ha-sensor-bridge camera-mqtt-bridge
```

### Step 2.3: Configure NAT Routing
```bash
# Enable IP forwarding
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward
sudo sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf

# Add NAT rules (IoT network → Storyteller MQTT)
sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 1883 -j DNAT --to-destination 192.168.1.50:1883
sudo iptables -t nat -A POSTROUTING -j MASQUERADE

# Save rules
sudo netfilter-persistent save 2>/dev/null || sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

---

## PHASE 3: SATELLITE SENSOR DEPLOYMENT

### Step 3.1: Power On Satellite
1. Ensure battery is charged (>3.7V actual voltage)
2. Place satellite in greenhouse
3. Wait 60 seconds for boot + WiFi connect

### Step 3.2: Verify Satellite Connection
```bash
# On Storyteller - watch for satellite messages
docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t "greenhouse/satellite-2/#" -v -C 5
# Expected: temperature, humidity, battery readings within 60s
```

---

## VERIFY SUCCESS

Run these checks in order. All must pass.

### Check 1: Docker Services
```bash
ssh joshcrow@100.94.172.114 "docker ps --format 'table {{.Names}}\t{{.Status}}'"
```
**PASS:** Both containers show "Up X minutes"

### Check 2: MQTT Broker
```bash
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t '#' -v -C 3 -W 30"
```
**PASS:** Receives sensor messages within 30 seconds

### Check 3: Sensor Data File
```bash
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 cat /app/data/status.json"
```
**PASS:** JSON contains `interior_temp`, `exterior_temp`, and/or `satellite-2` data

### Check 4: Image Archive
```bash
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 ls -la /app/data/archive/\$(date +%Y)/\$(date +%m)/\$(date +%d)/ 2>/dev/null | head -5"
```
**PASS:** Shows recent .jpg files (may be empty if camera just started)

### Check 5: Test Email
```bash
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py"
```
**PASS:** Email arrives in inbox with sensor data and narrative

### Check 6: Remote Access
```bash
# From phone hotspot or different network
ssh joshcrow@100.94.172.114 "echo 'Storyteller OK'"
ssh joshcrow@100.110.161.42 "echo 'Greenhouse Pi OK'"
```
**PASS:** Both commands succeed from external network

### Check 7: Scheduler Active
```bash
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 ps aux | grep scheduler"
```
**PASS:** Shows `python -u scripts/scheduler.py` process

---

## TROUBLESHOOTING

### Problem: "Connection refused" on MQTT
```bash
# Check Mosquitto is running
docker logs greenhouse-beach-mosquitto-1 --tail 20

# Check port is listening
ss -tlnp | grep 1883

# Restart Mosquitto
docker compose restart mosquitto
```

### Problem: No sensor data arriving
```bash
# On Greenhouse Pi - check bridge services
systemctl status ha-sensor-bridge --no-pager
systemctl status camera-mqtt-bridge --no-pager

# Check bridge logs
journalctl -u ha-sensor-bridge --since "10 min ago"

# Restart bridges
sudo systemctl restart ha-sensor-bridge camera-mqtt-bridge
```

### Problem: Satellite not connecting
```bash
# Check GREENHOUSE_IOT network is broadcasting
# On Greenhouse Pi:
iwconfig wlan0 | grep ESSID

# Put satellite in maintenance mode (stays awake for debugging)
docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
  -t "greenhouse/satellite-2/maintenance/state" -m "ON" -r

# IMPORTANT: Turn off when done (saves battery)
docker exec greenhouse-beach-mosquitto-1 mosquitto_pub \
  -t "greenhouse/satellite-2/maintenance/state" -m "OFF" -r
```

### Problem: Email not sending
```bash
# Check SMTP credentials
docker exec greenhouse-beach-storyteller-1 env | grep SMTP

# Check logs for email errors
docker logs greenhouse-beach-storyteller-1 --tail 50 | grep -i "email\|smtp\|error"

# Test SMTP connection
docker exec greenhouse-beach-storyteller-1 python -c "
import smtplib, ssl, os
ctx = ssl.create_default_context()
with smtplib.SMTP_SSL(os.getenv('SMTP_SERVER','smtp.gmail.com'), 465, context=ctx) as s:
    s.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
    print('SMTP OK')
"
```

### Problem: Can't SSH via Tailscale
```bash
# On the Pi (if you have local access)
tailscale status
sudo systemctl restart tailscaled
tailscale up

# Check Tailscale admin console
# https://login.tailscale.com/admin/machines
```

### Problem: NAT not forwarding
```bash
# On Greenhouse Pi - verify NAT rules
sudo iptables -t nat -L -n -v | grep 1883

# Test from IoT network device
nc -zv 10.0.0.1 1883
# Expected: Connection succeeded
```

---

## QUICK REFERENCE COMMANDS

### Daily Operations
```bash
# View live logs
ssh joshcrow@100.94.172.114 "docker compose -f ~/greenhouse-beach/docker-compose.yml logs -f --tail 20"

# Force send email
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py"

# Check sensor snapshot
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 cat /app/data/status.json | python3 -m json.tool"

# Restart everything
ssh joshcrow@100.94.172.114 "cd ~/greenhouse-beach && docker compose restart"
```

### Emergency Recovery
```bash
# Full rebuild (nuclear option)
ssh joshcrow@100.94.172.114 "cd ~/greenhouse-beach && docker compose down && docker compose build --no-cache && docker compose up -d"

# Check disk space
ssh joshcrow@100.94.172.114 "df -h /home"

# Clear old archives (if disk full)
ssh joshcrow@100.94.172.114 "find ~/greenhouse-beach/data/archive -mtime +30 -delete"
```

---

## POST-INSTALLATION CHECKLIST

- [ ] Static IP confirmed: `192.168.1.50`
- [ ] Both Docker containers running
- [ ] MQTT receiving sensor data
- [ ] Test email sent and received
- [ ] Tailscale accessible from phone hotspot
- [ ] Satellite sensor reporting battery + temp
- [ ] Camera images arriving in archive
- [ ] 7:00 AM scheduler job registered

**Installation Complete!** The system will send daily emails at 7:00 AM EST.

---

*Document Version: 1.0 | Created: December 19, 2025*
