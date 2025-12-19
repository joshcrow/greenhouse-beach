# 🏖️ Outer Banks Installation Guide

**Complete guide for deploying the Greenhouse Gazette at Mom's house.**

---

## 📋 Pre-Installation Checklist

### Hardware to Bring
- [ ] Storyteller Pi (Raspberry Pi 5) + power supply
- [ ] Ethernet cable (for initial setup)
- [ ] Satellite sensor (FireBeetle ESP32) + charged battery
- [ ] USB-C cable (for flashing satellite if needed)
- [ ] Laptop with SSH access configured

### Pre-Work Completed (Before Leaving Home)
- [ ] beachFi WiFi credentials added to Storyteller
- [ ] Tailscale installed and logged in on Storyteller
- [ ] Static IP configuration prepared
- [ ] Bridge config updates scripted
- [ ] ESPHome satellite config updated with GREENHOUSE_IOT credentials

---

## 🏠 Part 1: Pre-Work (Do This NOW at Home)

### 1.1 Add beachFi WiFi to Storyteller Pi

SSH into Storyteller and add your mom's WiFi network:

```bash
# SSH into Storyteller Pi
ssh joshcrow@greenhouse-storyteller

# Add beachFi network (will auto-connect when in range)
sudo nmcli device wifi connect "beachFi" password "YOUR_WIFI_PASSWORD" hidden no

# Verify it's saved
nmcli connection show
```

**Alternative: Pre-configure wpa_supplicant** (if using wpa_supplicant instead of NetworkManager):
```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```
Add:
```
network={
    ssid="beachFi"
    psk="YOUR_WIFI_PASSWORD"
    priority=10
}
```

### 1.2 Verify Tailscale is Ready

```bash
# Check Tailscale status
tailscale status

# Note your Tailscale IP (needed for remote access)
tailscale ip -4
# Should show: 100.94.172.114
```

### 1.3 Prepare Static IP Configuration Script

Create a script to switch to static IP once on-site:

```bash
cat << 'EOF' > ~/set_static_ip.sh
#!/bin/bash
# Run this AFTER connecting to beachFi

INTERFACE="wlan0"  # or eth0 if using ethernet
STATIC_IP="192.168.1.50"
GATEWAY="192.168.1.1"
DNS="8.8.8.8,8.8.4.4"

echo "Setting static IP: $STATIC_IP"

# For NetworkManager
sudo nmcli connection modify "beachFi" \
    ipv4.method manual \
    ipv4.addresses "$STATIC_IP/24" \
    ipv4.gateway "$GATEWAY" \
    ipv4.dns "$DNS"

sudo nmcli connection down "beachFi"
sudo nmcli connection up "beachFi"

echo "Static IP set. New IP:"
ip addr show $INTERFACE | grep "inet "
EOF
chmod +x ~/set_static_ip.sh
```

### 1.4 Prepare Bridge Config Update Script

Create a script to update Greenhouse Pi bridge configs:

```bash
cat << 'EOF' > ~/update_bridge_configs.sh
#!/bin/bash
# Run this on Greenhouse Pi after Storyteller has static IP

STORYTELLER_IP="192.168.1.50"

echo "Updating bridge configs to point to $STORYTELLER_IP..."

# Update sensor bridge
sudo sed -i "s/MQTT_HOST=.*/MQTT_HOST=$STORYTELLER_IP/" /opt/greenhouse/ha_sensor_bridge.env

# Update camera bridge  
sudo sed -i "s/MQTT_HOST=.*/MQTT_HOST=$STORYTELLER_IP/" /opt/greenhouse/camera_mqtt_bridge.env

# Restart services
sudo systemctl restart ha-sensor-bridge
sudo systemctl restart camera-mqtt-bridge

echo "Done. Checking service status..."
sudo systemctl status ha-sensor-bridge --no-pager -l
sudo systemctl status camera-mqtt-bridge --no-pager -l
EOF
chmod +x ~/update_bridge_configs.sh
```

### 1.5 Update Satellite Sensor ESPHome Config

The satellite sensor needs to connect to the **GREENHOUSE_IOT** network (10.0.0.x) hosted by Greenhouse Pi, NOT beachFi.

Update your ESPHome config for the satellite:

```yaml
wifi:
  ssid: "GREENHOUSE_IOT"
  password: "your_greenhouse_iot_password"
  
  # Static IP on the IoT network
  manual_ip:
    static_ip: 10.0.0.20
    gateway: 10.0.0.1
    subnet: 255.255.255.0
    dns1: 8.8.8.8

  # Fallback AP for debugging
  ap:
    ssid: "Satellite-Fallback"
    password: "fallback123"

# MQTT pointing to Storyteller (via NAT)
mqtt:
  broker: 10.0.0.1  # Greenhouse Pi routes to Storyteller
  port: 1883
  topic_prefix: greenhouse/satellite-2
```

Flash the satellite with updated config before leaving:
```bash
esphome run satellite-2.yaml
```

### 1.6 Test Local Network Simulation (Optional)

You can test the full flow at home by:
1. Creating a hotspot named "GREENHOUSE_IOT" on your phone
2. Connecting the satellite to it
3. Verifying MQTT messages reach Storyteller

---

## 🚗 Part 2: On-Site Installation (At Mom's)

### 2.1 Physical Setup

1. **Place Storyteller Pi** near the router (or use WiFi)
2. **Connect to beachFi** (should auto-connect if pre-configured)
3. **Verify connectivity:**
   ```bash
   # From your laptop, SSH via Tailscale
   ssh joshcrow@100.94.172.114
   
   # Check WiFi connection
   iwconfig wlan0
   ping -c 3 google.com
   ```

### 2.2 Set Static IP

```bash
# On Storyteller Pi
~/set_static_ip.sh

# Verify new IP
ip addr show wlan0
# Should show 192.168.1.50
```

### 2.3 Update Greenhouse Pi Bridge Configs

```bash
# SSH to Greenhouse Pi
ssh joshcrow@100.110.161.42  # via Tailscale

# Copy and run the update script
scp ~/update_bridge_configs.sh joshcrow@greenhouse-pi:~/
ssh joshcrow@greenhouse-pi "~/update_bridge_configs.sh"
```

**Or manually:**
```bash
ssh joshcrow@greenhouse-pi

# Update configs
sudo sed -i 's/MQTT_HOST=.*/MQTT_HOST=192.168.1.50/' /opt/greenhouse/ha_sensor_bridge.env
sudo sed -i 's/MQTT_HOST=.*/MQTT_HOST=192.168.1.50/' /opt/greenhouse/camera_mqtt_bridge.env

# Restart bridges
sudo systemctl restart ha-sensor-bridge camera-mqtt-bridge
```

### 2.4 Configure NAT Routing on Greenhouse Pi

The Greenhouse Pi needs to route traffic from the IoT network (10.0.0.x) to Storyteller (192.168.1.50):

```bash
ssh joshcrow@greenhouse-pi
sudo /opt/greenhouse/gateway_nat_setup.sh 192.168.1.50
```

**If the script doesn't exist, create it:**
```bash
cat << 'EOF' | sudo tee /opt/greenhouse/gateway_nat_setup.sh
#!/bin/bash
STORYTELLER_IP="${1:-192.168.1.50}"

echo "Setting up NAT routing to Storyteller at $STORYTELLER_IP"

# Enable IP forwarding
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward

# Make it persistent
sudo sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf

# Add NAT rules for MQTT (port 1883)
sudo iptables -t nat -A PREROUTING -i wlan1 -p tcp --dport 1883 -j DNAT --to-destination $STORYTELLER_IP:1883
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -i wlan1 -o wlan0 -j ACCEPT
sudo iptables -A FORWARD -i wlan0 -o wlan1 -m state --state RELATED,ESTABLISHED -j ACCEPT

# Save iptables rules
sudo netfilter-persistent save

echo "NAT routing configured."
EOF
sudo chmod +x /opt/greenhouse/gateway_nat_setup.sh
```

### 2.5 Deploy Satellite Sensor

1. **Power on the satellite** (ensure battery is charged)
2. **Wait for it to connect** to GREENHOUSE_IOT network
3. **Check Home Assistant** to see if it appears
4. **Verify MQTT messages** reach Storyteller:
   ```bash
   # On Storyteller
   docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t "greenhouse/#" -v
   ```

---

## ✅ Part 3: Test Plan (Day of Installation)

### Test 1: Network Connectivity
```bash
# From Storyteller
ping -c 3 192.168.1.1        # Gateway (beachFi router)
ping -c 3 192.168.1.X        # Greenhouse Pi local IP
ping -c 3 100.110.161.42     # Greenhouse Pi via Tailscale
ping -c 3 google.com         # Internet
```
**Expected:** All pings succeed

### Test 2: MQTT Broker
```bash
# On Storyteller - listen for any messages
docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t "#" -v &

# Wait 60 seconds, should see sensor data
```
**Expected:** Messages from interior, exterior, and satellite sensors

### Test 3: Sensor Bridge (Greenhouse Pi → Storyteller)
```bash
# Check bridge logs on Greenhouse Pi
ssh joshcrow@greenhouse-pi "journalctl -u ha-sensor-bridge -f"
```
**Expected:** "Published to MQTT" messages

### Test 4: Camera Bridge
```bash
# Test camera capture
ssh joshcrow@greenhouse-pi "python3 /opt/greenhouse/camera_mqtt_bridge.py --test"

# Check if image arrived on Storyteller
docker exec greenhouse-beach-storyteller-1 ls -la /app/data/incoming/
```
**Expected:** New image file appears

### Test 5: Email Delivery
```bash
# Force send a test email
docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py
```
**Expected:** Email arrives in inbox with all sensor data and hero image

### Test 6: Satellite Sensor
```bash
# Check satellite data in status.json
docker exec greenhouse-beach-storyteller-1 cat /app/data/status.json | grep satellite
```
**Expected:** Battery voltage > 1.7V (ADC), temperature, humidity values

### Test 7: Remote Access (Critical!)
```bash
# From your home network (or phone hotspot)
ssh joshcrow@100.94.172.114  # Storyteller via Tailscale
ssh joshcrow@100.110.161.42  # Greenhouse Pi via Tailscale
```
**Expected:** Both connections work from anywhere

### Test 8: Weekly Edition (Optional)
```bash
# Test the weekly edition timelapse
docker exec greenhouse-beach-storyteller-1 python scripts/publisher.py --weekly
```
**Expected:** Email with animated GIF and weekly summary

---

## 🔒 Part 4: Ensuring Remote Access

### 4.1 Tailscale Configuration

Both Pis should have Tailscale installed and running:

**Storyteller Pi:**
```bash
# Check status
tailscale status

# Enable SSH via Tailscale
sudo tailscale up --ssh

# Your Tailscale IPs:
# Storyteller: 100.94.172.114
# Greenhouse Pi: 100.110.161.42
```

### 4.2 SSH Key Access

Ensure your SSH keys are set up:
```bash
# From your laptop
ssh-copy-id joshcrow@100.94.172.114
ssh-copy-id joshcrow@100.110.161.42
```

### 4.3 Tailscale Auto-Start

Ensure Tailscale starts on boot:
```bash
sudo systemctl enable tailscaled
sudo systemctl status tailscaled
```

### 4.4 Emergency Access

If Tailscale fails, you can:
1. Ask Mom to plug in an ethernet cable
2. Use TeamViewer/AnyDesk on a nearby computer
3. SSH via the beachFi router's port forwarding (if configured)

---

## 🔄 Part 5: Maintenance & Development

### Remote Docker Management
```bash
# View logs
ssh joshcrow@100.94.172.114 "docker logs greenhouse-beach-storyteller-1 --tail 50"

# Restart services
ssh joshcrow@100.94.172.114 "cd greenhouse-beach && docker compose restart"

# Pull updates and rebuild
ssh joshcrow@100.94.172.114 "cd greenhouse-beach && git pull && docker compose build && docker compose up -d"
```

### Monitoring Commands
```bash
# Check sensor data
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 cat /app/data/status.json"

# Check 24h stats
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-storyteller-1 cat /app/data/stats_24h.json"

# Watch MQTT in real-time
ssh joshcrow@100.94.172.114 "docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t 'greenhouse/#' -v"
```

### Updating ESPHome Satellite Remotely
```bash
# OTA update via Home Assistant
# Or via ESPHome CLI if accessible
esphome run satellite-2.yaml --device 10.0.0.20
```

---

## 📊 Network Diagram (Final State)

```
                    INTERNET
                        │
                   ┌────┴────┐
                   │ beachFi │ (192.168.1.1)
                   │ Router  │
                   └────┬────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   ┌────┴────┐    ┌─────┴─────┐    ┌────┴────┐
   │Storyteller│    │Greenhouse │    │  Other  │
   │   Pi 5   │    │   Pi 4    │    │ Devices │
   │.1.50     │    │.1.X       │    │         │
   │Tailscale │    │Tailscale  │    │         │
   │100.94.   │    │100.110.   │    │         │
   └────┬────┘    └─────┬─────┘    └─────────┘
        │               │
        │ MQTT:1883     │ hostapd
        │               │
        │         ┌─────┴─────┐
        │         │GREENHOUSE │
        │         │   _IOT    │
        │         │10.0.0.0/24│
        │         └─────┬─────┘
        │               │
        │    ┌──────────┼──────────┐
        │    │          │          │
        │ ┌──┴──┐   ┌───┴───┐  ┌───┴───┐
        │ │Sat-1│   │ Sat-2 │  │ Sat-N │
        │ │10.0.│   │10.0.  │  │10.0.  │
        │ │0.20 │   │ 0.21  │  │ 0.X   │
        │ └──┬──┘   └───┬───┘  └───┬───┘
        │    │          │          │
        └────┴──────────┴──────────┘
                NAT via Greenhouse Pi
```

---

## ⚠️ Troubleshooting

### "No sensor data in email"
```bash
# Check MQTT broker is receiving
docker exec greenhouse-beach-mosquitto-1 mosquitto_sub -t "#" -v

# Check bridge services on Greenhouse Pi
ssh greenhouse-pi "systemctl status ha-sensor-bridge"
```

### "Satellite sensor offline"
1. Check battery voltage (needs > 3.4V actual)
2. Verify GREENHOUSE_IOT WiFi is broadcasting
3. Check ESPHome logs in Home Assistant
4. Try power cycling the satellite

### "Can't SSH remotely"
1. Check Tailscale status: `tailscale status`
2. Verify internet connectivity on the Pi
3. Try Tailscale admin console: https://login.tailscale.com/admin/machines

### "Camera images not arriving"
```bash
# Test camera manually
ssh greenhouse-pi "python3 /opt/greenhouse/camera_mqtt_bridge.py --test"

# Check Home Assistant camera entity
# Verify MQTT topic is correct
```

---

## 📝 Quick Reference

| Device | Local IP | Tailscale IP | Role |
|--------|----------|--------------|------|
| Storyteller Pi | 192.168.1.50 | 100.94.172.114 | MQTT broker, AI, Email |
| Greenhouse Pi | 192.168.1.X | 100.110.161.42 | Camera, HA, IoT gateway |
| Satellite-2 | 10.0.0.20 | N/A | Battery sensor |

| Service | Port | Notes |
|---------|------|-------|
| MQTT | 1883 | Mosquitto on Storyteller |
| SSH | 22 | Via Tailscale |
| Home Assistant | 8123 | On Greenhouse Pi |

---

*Last Updated: December 19, 2025*
