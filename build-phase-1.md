# **Build guide: Pi setup, isolated network, and first sensor (Hybrid Workflow)**

## **Objective**

This guide details the initial setup for the greenhouse monitoring project. The goal is to install the core controller, create an isolated wireless network, and build the first prototype sensor node.

**The setup:**

We will run Home Assistant and ESPHome on the Raspberry Pi so it acts as the hub. We will use a **dual-WiFi setup**:

1. **USB Wi-Fi Adapter:** Connects the Pi to your home internet (for updates and remote access).  
2. **Built-in Wi-Fi:** Broadcasts a private network (GREENHOUSE\_IOT) to keep your sensors isolated.

*Note: We use your Mac to compile the firmware because it is significantly faster than the Pi.*

**Estimated time:** 1.5 \- 2 hours

## **1\. Required hardware**

* **Controller:**  
  * 1x Raspberry Pi 4 or 5  
  * 1x 32GB (or larger) A2-rated microSD card  
  * 1x Official Raspberry Pi USB-C power supply  
* **Networking:**  
  * 1x USB Wi-Fi Adapter (Specifically the [TP-Link TL-WN725N](https://www.amazon.com/dp/B01GC8XH0S?ref_=ppx_hzsearch_conn_dt_b_fed_asin_title_1) or similar).  
* **Sensor node:**  
  * 1x ESP32-WROOM-32 development board  
  * 1x Breadboard  
  * 1x Jumper wire kit  
  * 1x Micro-USB or USB-C cable (data capable)  
* **Sensor:**  
  * 1x BME280 sensor

## **2\. Set up the Raspberry Pi OS \+ Docker**

1. **Get the imager:** Download and install **Raspberry Pi Imager** on your Mac.  
2. **Flash the OS:**  
   * Open Raspberry Pi Imager.  
   * Choose OS: **Raspberry Pi OS (other) \-\> Raspberry Pi OS Lite (64-bit)**.  
   * Choose Storage: Select your microSD card.  
   * **CRITICAL:** Click the **Gear icon** (Cmd+Shift+X) for settings:  
     * Enable SSH (Use password authentication).  
     * Set username (e.g., pi) and password.  
     * Set hostname: greenhouse-pi.  
     * **Configure your home Wi-Fi.** (This allows the USB adapter to connect to your home network automatically).  
   * Write and verify.  
3. **Boot the Pi:**  
   * Insert SD card.  
   * **Plug in the TP-Link USB Wi-Fi Adapter.**  
   * Connect power.  
4. **Log in:**  
   * Wait 2-3 minutes for boot.  
   * Open Terminal on Mac.  
   * ssh pi@greenhouse-pi.local  
5. **Install Docker (on the Pi):**  
   curl \-fsSL \[https://get.docker.com\](https://get.docker.com) \-o get-docker.sh  
   sudo sh get-docker.sh  
   sudo usermod \-aG docker pi

   *Log out (exit) and log back in for changes to take effect.*

## **3\. Install Home Assistant**

1. **Run the container:**  
   docker run \-d \\  
     \--name homeassistant \\  
     \--restart=unless-stopped \\  
     \-e TZ=America/New\_York \\  
     \-v /home/pi/ha\_config:/config \\  
     \--network=host \\  
     ghcr.io/home-assistant/home-assistant:stable

2. **Onboard:** Go to http://greenhouse-pi.local:8123 and create your account.

## **4\. Install ESPHome Dashboard**

We need ESPHome running on the Pi to manage the nodes and handle OTA (Over-the-Air) updates later.

1. **Run the container:**  
   docker run \-d \\  
     \--name esphome \\  
     \--restart=unless-stopped \\  
     \-v /home/pi/esphome\_config:/config \\  
     \--network=host \\  
     ghcr.io/esphome/esphome:stable

2. **Verify:** Check http://greenhouse-pi.local:6052.

## **5\. Configure the isolated IoT network**

We will configure the Pi's **built-in Wi-Fi (wlan0)** to act as the Access Point for your sensors, while the **USB Adapter (wlan1)** handles the internet connection.

1. **Install tools:**  
   sudo apt update  
   sudo apt install hostapd dnsmasq

2. Configure hostapd (The Access Point):  
   sudo nano /etc/hostapd/hostapd.conf  
   interface=wlan0  
   driver=nl80211  
   ssid=GREENHOUSE\_IOT  
   hw\_mode=g  
   channel=7  
   wmm\_enabled=1  
   macaddr\_acl=0  
   auth\_algs=1  
   ignore\_broadcast\_ssid=0  
   wpa=2  
   wpa\_passphrase=YourSecurePassword  
   wpa\_key\_mgmt=WPA-PSK  
   rsn\_pairwise=CCMP

3. Configure dnsmasq (The IP Address Assigner):  
   sudo nano /etc/dnsmasq.conf  
   (Add to end):  
   interface=wlan0  
   dhcp-range=10.0.0.50,10.0.0.150,255.255.255.0,12h

4. Point system to config:  
   sudo nano /etc/default/hostapd  
   (Change DAEMON\_CONF line):  
   DAEMON\_CONF="/etc/hostapd/hostapd.conf"

5. Set Static IP for the built-in WiFi:  
   sudo nano /etc/dhcpcd.conf  
   (Add to end):  
   interface wlan0  
   static ip\_address=10.0.0.1/24  
   nohook wpa\_supplicant

   *Explanation: The nohook wpa\_supplicant line tells the Pi "Do not use the built-in WiFi for internet." The OS will then automatically use your USB adapter (wlan1) for the internet connection you set up in the Imager.*  
6. **Enable and Reboot:**  
   sudo systemctl unmask hostapd  
   sudo systemctl enable hostapd  
   sudo systemctl enable dnsmasq  
   sudo reboot

## **6\. Build the sensor firmware**

### **6.a. Hardware assembly**

Wire the BME280 to the ESP32:

* **3.3V Pin (ESP32)** \-\> **VIN (Sensor)**  
* **GND Pin (ESP32)** \-\> **GND (Sensor)**  
* **GPIO 22** \-\> **SCL**  
* **GPIO 21** \-\> **SDA**

### **6.b. Set up your Mac**

1. Open Terminal on your Mac.  
2. Install Docker Desktop (if not already installed):  
   brew install \--cask docker

3. Open the **Docker** app from your Applications folder and let it start.  
4. Create a build folder on your Desktop:  
   mkdir \~/Desktop/esphome-build

### **6.c. Generate config on the Pi**

1. Go to http://greenhouse-pi.local:6052.  
2. Click **\+ New Device**. Name it greenhouse\_node\_1.  
3. **Wi-Fi:** Enter the **Isolated Network** credentials:  
   * SSID: GREENHOUSE\_IOT  
   * Password: YourSecurePassword  
4. Click **Install**, then click **Skip**.  
5. Click **Edit** on the new node card.  
6. Paste the sensor code at the bottom of the YAML:  
   \# Enable I2C  
   i2c:  
     sda: 21  
     scl: 22  
     scan: true

   \# Sensor configuration  
   sensor:  
     \- platform: bme280  
       temperature:  
         name: "Greenhouse Temperature"  
       pressure:  
         name: "Greenhouse Pressure"  
       humidity:  
         name: "Greenhouse Humidity"  
       address: 0x76  
       update\_interval: 30s

7. **Save**, but do **not** click Install.  
8. **Copy all the code** from the file editor.

### **6.d. Compile on your Mac**

1. Open a text editor on your Mac.  
2. Paste the YAML code you just copied.  
3. Save the file as greenhouse\_node\_1.yaml inside the \~/Desktop/esphome-build folder.  
4. In your Mac Terminal, run the compile command:  
   cd \~/Desktop/esphome-build  
   docker run \--rm \-v "$PWD":/config \-it ghcr.io/esphome/esphome compile greenhouse\_node\_1.yaml

   *(Note: The first time you run this, it will download a large file, which may take a minute. Subsequent runs will take \~15 seconds).*

### **6.e. Flash the chip**

1. **Retrieve the file:** Run this command in your Mac Terminal to copy the hidden firmware file to your folder so it's easier to find:  
   cp .esphome/build/greenhouse\_node\_1/.pioenvs/greenhouse\_node\_1/firmware-factory.bin ./greenhouse\_node\_1.bin

2. Open Chrome or Edge and go to [**https://web.esphome.io/**](https://web.esphome.io/).  
3. Plug your ESP32 into the Mac.  
4. Click **Connect** \-\> Select Device \-\> **Install**.  
5. Select **Choose File** and upload the greenhouse\_node\_1.bin file from your esphome-build folder.  
6. Click **Install**.

Once finished, unplug the ESP32 and plug it into a wall charger. It will automatically connect to the GREENHOUSE\_IOT network.

## **7\. The result**

1. Go to http://greenhouse-pi.local:8123 (Home Assistant).  
2. Go to **Settings \> Devices & Services**.  
3. You will see greenhouse\_node\_1 discovered. Click **Configure**.  
4. Your sensor data is now live\!

## **8\. Troubleshooting**

* **Flash fails or sticks on "Connecting":** Many ESP32 boards have a **BOOT** button. If the web installer gets stuck on "Connecting...", hold down the BOOT button on the board for 3 seconds, then release it.  
* **Mac Docker Error:** If the docker run command fails on Mac, ensure the Docker app is running (look for the whale icon in the menu bar).  
* **Pi not discovering node:** Ensure the ESP32 is powered and within range of the Pi. Check the logs on the Pi dashboard (http://greenhouse-pi.local:6052)—even if the Pi didn't build the firmware, it will show the logs once the device connects to WiFi.
