#!/bin/bash
# Gateway NAT Setup Script for Greenhouse Pi (Node A)
#
# This script configures the Greenhouse Pi to:
# 1. Enable IP forwarding
# 2. Set up NAT (MASQUERADE) for IoT devices to reach the internet
# 3. Port forward MQTT (1883) from IoT network to Storyteller
#
# Usage: sudo ./gateway_nat_setup.sh <STORYTELLER_IP>
# Example: sudo ./gateway_nat_setup.sh 192.168.1.50

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root (use sudo)"
   exit 1
fi

# Check for required argument
if [[ $# -lt 1 ]]; then
    echo "Usage: sudo $0 <STORYTELLER_IP>"
    echo "Example: sudo $0 192.168.1.50"
    exit 1
fi

STORYTELLER_IP="$1"
IOT_INTERFACE="${IOT_INTERFACE:-wlan0}"      # AP interface (IoT network)
WAN_INTERFACE="${WAN_INTERFACE:-eth0}"       # Home network interface
IOT_NETWORK="${IOT_NETWORK:-10.0.0.0/24}"    # IoT subnet
MQTT_PORT=1883

log_info "Configuring NAT gateway..."
log_info "  Storyteller IP: $STORYTELLER_IP"
log_info "  IoT Interface:  $IOT_INTERFACE"
log_info "  WAN Interface:  $WAN_INTERFACE"
log_info "  IoT Network:    $IOT_NETWORK"

# Step 1: Enable IP forwarding
log_info "Enabling IP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward

# Make persistent across reboots
if ! grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    log_info "Added ip_forward to /etc/sysctl.conf"
fi

# Step 2: Flush existing NAT rules (careful - this resets everything)
log_warn "Flushing existing NAT rules..."
iptables -t nat -F

# Step 3: Set up MASQUERADE for IoT devices to access internet via home network
log_info "Setting up MASQUERADE for IoT → WAN..."
iptables -t nat -A POSTROUTING -o "$WAN_INTERFACE" -j MASQUERADE

# Step 4: Port forward MQTT from IoT network to Storyteller
log_info "Setting up MQTT port forward (10.0.0.1:$MQTT_PORT → $STORYTELLER_IP:$MQTT_PORT)..."
iptables -t nat -A PREROUTING -i "$IOT_INTERFACE" -p tcp --dport "$MQTT_PORT" \
    -j DNAT --to-destination "$STORYTELLER_IP:$MQTT_PORT"

# Step 5: Allow forwarding for the DNAT'd traffic
log_info "Allowing forwarded MQTT traffic..."
iptables -A FORWARD -p tcp -d "$STORYTELLER_IP" --dport "$MQTT_PORT" -j ACCEPT

# Step 6: Allow established connections back
iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT

# Step 7: Save rules for persistence (Debian/Ubuntu)
log_info "Saving iptables rules..."
if command -v iptables-save &> /dev/null; then
    mkdir -p /etc/iptables
    iptables-save > /etc/iptables/rules.v4
    log_info "Rules saved to /etc/iptables/rules.v4"
    
    # Ensure rules are restored on boot
    if [[ ! -f /etc/network/if-pre-up.d/iptables ]]; then
        cat > /etc/network/if-pre-up.d/iptables << 'EOF'
#!/bin/sh
/sbin/iptables-restore < /etc/iptables/rules.v4
EOF
        chmod +x /etc/network/if-pre-up.d/iptables
        log_info "Created iptables restore script"
    fi
fi

# Display current NAT rules
log_info "Current NAT rules:"
echo "----------------------------------------"
iptables -t nat -L -n -v
echo "----------------------------------------"

log_info "NAT gateway setup complete!"
log_info ""
log_info "To verify:"
log_info "  1. From a satellite on IoT network, test: nc -zv 10.0.0.1 $MQTT_PORT"
log_info "  2. On Storyteller, watch: docker logs -f greenhouse-beach-mosquitto-1"
log_info ""
log_info "To undo: sudo iptables -t nat -F && sudo iptables -F FORWARD"
