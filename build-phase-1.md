# Greenhouse Monitor Infrastructure Guide

| Parameter | Specification |
| :--- | :--- |
| **Target OS** | Raspberry Pi OS Lite (64-bit) - Debian 12/13 (Bookworm/Trixie) |
| **Architecture** | Hybrid (Build on Mac, Run on Pi) |
| **Network Stack** | NetworkManager Native (No hostapd/dnsmasq) |

## PART 1: Infrastructure Setup

*Perform these steps once to provision the gateway.*

### 1. Base System Prep

1.  **Flash OS:** Raspberry Pi OS Lite (64-bit).

2.  **Imager Settings:**

      * Enable SSH.
      * Set Username/Password.
      * Configure `wlan1` (Home WiFi).

3.  **Update & Install Dependencies:**
    SSH into the Pi (`ssh pi@greenhouse-pi.local`) and run:

    ```bash
    sudo apt update && sudo apt upgrade -y
    sudo apt purge dhcpcd5 -y # Remove legacy network manager to prevent conflicts
    curl -fsSL [https://get.docker.com](https://get.docker.com) | sudo sh
    sudo usermod -aG docker $USER
    sudo reboot
    ```

### 2. Network Configuration (The IoT Gateway)

We use `nmcli` to create a managed Access Point with WPA2, Static IP, and DHCP.

1.  **Enable NetworkManager Management:**

      * Edit config: `sudo nano /etc/NetworkManager/NetworkManager.conf`
      * Change `managed=false` to `managed=true` under `[ifupdown]`.
      * Save & Exit.

2.  **Create the AP:**
    Run this entire block as a single command.

    > **Note:** Replace `YOUR_PASSWORD` below before running.

    ```bash
    sudo nmcli con add type wifi ifname wlan0 con-name "GREENHOUSE_IOT" autoconnect yes ssid "GREENHOUSE_IOT" && \
    sudo nmcli con modify "GREENHOUSE_IOT" 802-11-wireless.mode ap && \
    sudo nmcli con modify "GREENHOUSE_IOT" wifi-sec.key-mgmt wpa-psk && \
    sudo nmcli con modify "GREENHOUSE_IOT" wifi-sec.psk "YOUR_PASSWORD" && \
    sudo nmcli con modify "GREENHOUSE_IOT" wifi-sec.pmf 1 && \
    sudo nmcli con modify "GREENHOUSE_IOT" wifi-sec.proto rsn && \
    sudo nmcli con modify "GREENHOUSE_IOT" wifi-sec.pairwise ccmp && \
    sudo nmcli con modify "GREENHOUSE_IOT" wifi-sec.group ccmp && \
    sudo nmcli con modify "GREENHOUSE_IOT" ipv4.addresses 10.0.0.1/24 && \
    sudo nmcli con modify "GREENHOUSE_IOT" ipv4.gateway 10.0.0.1 && \
    sudo nmcli con modify "GREENHOUSE_IOT" ipv4.method shared && \
    sudo nmcli con modify "GREENHOUSE_IOT" ipv4.never-default yes && \
    sudo nmcli con modify "GREENHOUSE_IOT" 802-11-wireless.band bg && \
    sudo nmcli con modify "GREENHOUSE_IOT" 802-11-wireless.channel 6 && \
    sudo nmcli con up "GREENHOUSE_IOT"
    ```

3.  **Verify:**
    Run `ip addr show wlan0`.

      * *Expect:* `inet 10.0.0.1/24`.

### 3. Deploy Containers

Run both containers on the host network.

**Home Assistant**

```bash
docker run -d --name homeassistant \
  --restart=unless-stopped \
  -v /home/pi/ha_config:/config \
  --network=host \
  ghcr.io/home-assistant/home-assistant:stable
```

**ESPHome**

```bash
docker run -d --name esphome \
  --restart=unless-stopped \
  -v /home/pi/esphome_config:/config \
  --network=host \
  ghcr.io/esphome/esphome:stable
```

**Access Points:**

  * **Home Assistant:** http://greenhouse-pi.local:8123
  * **ESPHome:** http://greenhouse-pi.local:6052

-----

## PART 2: Sensor Provisioning (Repeat per Device)

**Workflow:** Generate Config (Pi) -> Build (Mac) -> Flash (Mac) -> Integrate (Pi)

### 1. Generate Config (On Pi Dashboard)

1.  Go to http://greenhouse-pi.local:6052.
2.  **+ New Device**:
      * **Name:** `greenhouse_node_X` (Increment number).
      * **SSID:** `GREENHOUSE_IOT`
      * **Password:** `YOUR_PASSWORD`
3.  **Get Key:** Click **Edit** on the new card. Copy the `api: encryption: key`.
4.  **Get YAML:** Copy the entire YAML content to your clipboard.

### 2. Compile Firmware (On Mac)

1.  Create/Update file: `~/Desktop/esphome-build/greenhouse_node_X.yaml`.
2.  Paste YAML content.
3.  Compile via Docker:
    ```bash
    cd ~/Desktop/esphome-build
    docker run --rm -v "$PWD":/config -it ghcr.io/esphome/esphome compile greenhouse_node_X.yaml
    ```
4.  Extract the `.bin` file from the build folder.

### 3. Flash (On Mac)

1.  Connect ESP32 via USB.
2.  Go to [https://web.esphome.io](https://web.esphome.io).
3.  Click **Connect** -> **Install** -> Select `.bin` file.
      * *Tip: Hold the BOOT button on the ESP32 if the connection hangs.*

### 4. Integrate (On Pi / Home Assistant)

1.  **Retrieve IP:**
    Wait 30s after flashing, then run on the Pi:

    ```bash
    cat /var/lib/NetworkManager/dnsmasq-wlan0.leases
    ```

    *Identify the new IP address (e.g., `10.0.0.88`).*

2.  **Add to Home Assistant:**

      * Go to **Settings** > **Devices & Services** > **+ Add Integration**.
      * Select **ESPHome**.
      * **Host:** `10.0.0.88` (from previous step).
      * **Port:** `6053`.
      * **Key:** Paste key from Step 1.
