Build guide: Pi setup, isolated network, and first sensor (Hybrid Workflow)ObjectiveThis guide details the initial setup for the greenhouse monitoring project. The goal is to install the core controller, create an isolated wireless network, and build the first prototype sensor node.The setup:We will run Home Assistant and ESPHome on the Raspberry Pi so it acts as the hub. We will use a dual-WiFi setup:USB Wi-Fi Adapter: Connects the Pi to your home internet (for updates and remote access).Built-in Wi-Fi: Broadcasts a private network (GREENHOUSE_IOT) to keep your sensors isolated.Note: We use your Mac to compile the firmware because it is significantly faster than the Pi.Estimated time: 1.5 - 2 hours1. Required hardwareController:1x Raspberry Pi 4 or 51x 32GB (or larger) A2-rated microSD card1x Official Raspberry Pi USB-C power supplyNetworking:1x USB Wi-Fi Adapter (Specifically the TP-Link TL-WN725N or similar).Sensor node:1x ESP32-WROOM-32 development board1x Breadboard1x Jumper wire kit1x Micro-USB or USB-C cable (data capable)Sensor:1x BME280 sensor2. Set up the Raspberry Pi OS + DockerGet the imager: Download and install Raspberry Pi Imager on your Mac.Flash the OS:Open Raspberry Pi Imager.Choose OS: Raspberry Pi OS (other) -> Raspberry Pi OS Lite (64-bit).Choose Storage: Select your microSD card.CRITICAL: Click the Gear icon (Cmd+Shift+X) for settings:Enable SSH (Use password authentication).Set username (e.g., pi) and password.Set hostname: greenhouse-pi.Configure your home Wi-Fi. (This allows the USB adapter to connect to your home network automatically).Write and verify.Boot the Pi:Insert SD card.Plug in the TP-Link USB Wi-Fi Adapter.Connect power.Log in:Wait 2-3 minutes for boot.Open Terminal on Mac.ssh pi@greenhouse-pi.localInstall Docker (on the Pi):curl -fsSL [https://get.docker.com](https://get.docker.com) -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker pi
Log out (exit) and log back in for changes to take effect.3. Install Home AssistantRun the container:docker run -d \
  --name homeassistant \
  --restart=unless-stopped \
  -e TZ=America/New_York \
  -v /home/pi/ha_config:/config \
  --network=host \
  ghcr.io/home-assistant/home-assistant:stable
Onboard: Go to http://greenhouse-pi.local:8123 and create your account.4. Install ESPHome DashboardWe need ESPHome running on the Pi to manage the nodes and handle OTA (Over-the-Air) updates later.Run the container:docker run -d \
  --name esphome \
  --restart=unless-stopped \
  -v /home/pi/esphome_config:/config \
  --network=host \
  ghcr.io/esphome/esphome:stable
Verify: Check http://greenhouse-pi.local:6052.5. Configure the isolated IoT networkWe will configure the Pi's built-in Wi-Fi (wlan0) to act as the Access Point for your sensors, while the USB Adapter (wlan1) handles the internet connection.Install tools:sudo apt update
sudo apt install hostapd dnsmasq
Configure hostapd (The Access Point):sudo nano /etc/hostapd/hostapd.confinterface=wlan0
driver=nl80211
ssid=GREENHOUSE_IOT
hw_mode=g
channel=7
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=YourSecurePassword
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
Configure dnsmasq (The IP Address Assigner):sudo nano /etc/dnsmasq.conf(Add to end):interface=wlan0
dhcp-range=10.0.0.50,10.0.0.150,255.255.255.0,12h
Point system to config:sudo nano /etc/default/hostapd(Change DAEMON_CONF line):DAEMON_CONF="/etc/hostapd/hostapd.conf"
Set Static IP for the built-in WiFi:sudo nano /etc/dhcpcd.conf(Add to end):interface wlan0
static ip_address=10.0.0.1/24
nohook wpa_supplicant
Explanation: The nohook wpa_supplicant line tells the Pi "Do not use the built-in WiFi for internet." The OS will then automatically use your USB adapter (wlan1) for the internet connection you set up in the Imager.Enable and Reboot:sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq
sudo reboot
6. Build the sensor firmware6.a. Hardware assemblyWire the BME280 to the ESP32:3.3V Pin (ESP32) -> VIN (Sensor)GND Pin (ESP32) -> GND (Sensor)GPIO 22 -> SCLGPIO 21 -> SDA6.b. Set up your MacOpen Terminal on your Mac.Install Docker Desktop (if not already installed):brew install --cask docker
Open the Docker app from your Applications folder and let it start.Create a build folder on your Desktop:mkdir ~/Desktop/esphome-build
6.c. Generate config on the PiGo to http://greenhouse-pi.local:6052.Click + New Device. Name it greenhouse_node_1.Wi-Fi: Enter the Isolated Network credentials:SSID: GREENHOUSE_IOTPassword: YourSecurePasswordClick Install, then click Skip.Click Edit on the new node card.Paste the sensor code at the bottom of the YAML:# Enable I2C
i2c:
  sda: 21
  scl: 22
  scan: true

# Sensor configuration
sensor:
  - platform: bme280
    temperature:
      name: "Greenhouse Temperature"
    pressure:
      name: "Greenhouse Pressure"
    humidity:
      name: "Greenhouse Humidity"
    address: 0x76
    update_interval: 30s
Save, but do not click Install.Copy all the code from the file editor.6.d. Compile on your MacOpen a text editor on your Mac.Paste the YAML code you just copied.Save the file as greenhouse_node_1.yaml inside the ~/Desktop/esphome-build folder.In your Mac Terminal, run the compile command:cd ~/Desktop/esphome-build
docker run --rm -v "$PWD":/config -it ghcr.io/esphome/esphome compile greenhouse_node_1.yaml
(Note: The first time you run this, it will download a large file, which may take a minute. Subsequent runs will take ~15 seconds).6.e. Flash the chipRetrieve the file: Run this command in your Mac Terminal to copy the hidden firmware file to your folder so it's easier to find:cp .esphome/build/greenhouse_node_1/.pioenvs/greenhouse_node_1/firmware-factory.bin ./greenhouse_node_1.bin
Open Chrome or Edge and go to https://web.esphome.io/.Plug your ESP32 into the Mac.Click Connect -> Select Device -> Install.Select Choose File and upload the greenhouse_node_1.bin file from your esphome-build folder.Click Install.Once finished, unplug the ESP32 and plug it into a wall charger. It will automatically connect to the GREENHOUSE_IOT network.7. The resultGo to http://greenhouse-pi.local:8123 (Home Assistant).Go to Settings > Devices & Services.You will see greenhouse_node_1 discovered. Click Configure.Your sensor data is now live!8. TroubleshootingFlash fails or sticks on "Connecting": Many ESP32 boards have a BOOT button. If the web installer gets stuck on "Connecting...", hold down the BOOT button on the board for 3 seconds, then release it.Mac Docker Error: If the docker run command fails on Mac, ensure the Docker app is running (look for the whale icon in the menu bar).Pi not discovering node: Ensure the ESP32 is powered and within range of the Pi. Check the logs on the Pi dashboard (http://greenhouse-pi.local:6052)—even if the Pi didn't build the firmware, it will show the logs once the device connects to WiFi.
