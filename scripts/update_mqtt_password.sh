#!/bin/bash
# =============================================================================
# MQTT Password Update Script
# =============================================================================
# Updates MQTT password across all system components:
# 1. Mosquitto broker (configs/passwd)
# 2. Docker environment (.env)
# 3. ESPHome secrets (esphome/secrets.yaml)
#
# Usage: ./scripts/update_mqtt_password.sh [new_password]
# If no password provided, generates a random one
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "  MQTT Password Update"
echo "=========================================="

# Generate or use provided password
if [ -n "$1" ]; then
    NEW_PASSWORD="$1"
    echo -e "${YELLOW}Using provided password${NC}"
else
    NEW_PASSWORD=$(openssl rand -base64 24)
    echo -e "${GREEN}Generated new password: ${NEW_PASSWORD}${NC}"
fi

echo ""
echo "This will update MQTT password in:"
echo "  1. .env (Docker compose)"
echo "  2. esphome/secrets.yaml (ESPHome devices)"
echo "  3. Mosquitto passwd file (broker)"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# 1. Update .env
echo ""
echo -e "${YELLOW}[1/4] Updating .env...${NC}"
if [ -f "$PROJECT_DIR/.env" ]; then
    sed -i "s|^MQTT_PASSWORD=.*|MQTT_PASSWORD=${NEW_PASSWORD}|" "$PROJECT_DIR/.env"
    echo -e "${GREEN}  ✓ Updated .env${NC}"
else
    echo -e "${RED}  ✗ .env not found!${NC}"
fi

# 2. Update esphome/secrets.yaml
echo -e "${YELLOW}[2/4] Updating esphome/secrets.yaml...${NC}"
if [ -f "$PROJECT_DIR/esphome/secrets.yaml" ]; then
    sed -i "s|^mqtt_password:.*|mqtt_password: \"${NEW_PASSWORD}\"|" "$PROJECT_DIR/esphome/secrets.yaml"
    echo -e "${GREEN}  ✓ Updated esphome/secrets.yaml${NC}"
else
    echo -e "${RED}  ✗ esphome/secrets.yaml not found!${NC}"
fi

# 3. Update Mosquitto passwd (requires docker)
echo -e "${YELLOW}[3/4] Updating Mosquitto password file...${NC}"
if docker ps | grep -q mosquitto; then
    docker exec greenhouse-beach-mosquitto-1 mosquitto_passwd -b /mosquitto/config/passwd greenhouse "$NEW_PASSWORD" 2>/dev/null || \
    docker exec greenhouse-beach_mosquitto_1 mosquitto_passwd -b /mosquitto/config/passwd greenhouse "$NEW_PASSWORD" 2>/dev/null || \
    echo -e "${RED}  ✗ Could not update Mosquitto passwd (container name mismatch)${NC}"
    echo -e "${GREEN}  ✓ Updated Mosquitto passwd${NC}"
else
    echo -e "${YELLOW}  ⚠ Mosquitto not running - update manually after start${NC}"
fi

# 4. Restart services
echo -e "${YELLOW}[4/4] Restarting services...${NC}"
if docker ps | grep -q greenhouse; then
    cd "$PROJECT_DIR"
    docker compose restart
    echo -e "${GREEN}  ✓ Services restarted${NC}"
else
    echo -e "${YELLOW}  ⚠ Docker services not running${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}MQTT Password Updated!${NC}"
echo "=========================================="
echo ""
echo "IMPORTANT: ESPHome devices need to be re-flashed!"
echo ""
echo "Steps to update satellites:"
echo "  1. cd esphome/sensors/"
echo "  2. Update password in your YAML or use secrets.yaml"
echo "  3. Compile: docker run --rm -v \"\$PWD\":/config ghcr.io/esphome/esphome compile satellite-sensor-2.yaml"
echo "  4. Flash via web.esphome.io or OTA"
echo ""
