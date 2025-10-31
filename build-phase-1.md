# **Build guide: Pi setup, isolated network, and first sensor**

## **Objective**

This guide details the initial setup for the greenhouse monitoring project. The goal is to install the core controller, create an isolated wireless network, install the automation software (Home Assistant and ESPHome), and build the first prototype sensor node.  
This architecture is built on two key decisions:

1. **Container-based software:** We will run Home Assistant and ESPHome in Docker containers. This provides flexibility and control over the host operating system.  
2. **Isolated network:** The Raspberry Pi will create its own private WiFi network (GREENHOUSE\_IOT). This makes the system robust, secure, and independent of the home's main WiFi network.

## **1\. Required hardware**

This list covers the essential hardware required for *this* guide.

* **Controller:**  
  * 1x Raspberry Pi 4 (4GB+ model) or Raspberry Pi 5  
  * 1x 32GB (or larger) A2-rated microSD card  
  * 1x Official Raspberry Pi USB-C power supply  
  * 1x Ethernet cable  
* **Sensor node:**  
  * 1x ESP32-WROOM-32 development board (with USB)  
  * 1x Breadboard (for prototyping)  
  * 1x Jumper wire kit (M-M, M-F, F-F)  
  * 1x Micro-USB or USB-C cable (for the ESP32)  
  * 1x 5V USB power adapter (e.g., phone charger)  
* **Sensor:**  
  * 1x BME280 sensor (temperature, humidity, pressure)

## **2\. Set up the 'brain' (Raspberry Pi OS \+ Docker)**

We will install the standard Raspberry Pi operating system and then run Home Assistant inside a "container."

1. **Get the imager:** On your Mac, download and install **Raspberry Pi Imager**.  
2. **Flash the OS:**  
   * Insert your microSD card into your Mac.  
   * Open Raspberry Pi Imager.  
   * Click **Choose OS** \-\> **Raspberry Pi OS (other)** \-\> **Raspberry Pi OS Lite (64-bit)**.  
   * Click **Choose Storage** and select your microSD card.  
   * **CRITICAL STEP:** Click the **Gear icon** (or press **Cmd+Shift+X**) to open the Advanced Options.  
   * Check **Enable SSH** and select **Use password authentication**.  
   * Set a **username** (e.g., pi) and a secure **password**.  
   * Set a **hostname** (e.g., greenhouse-pi). Check "Enable".  
   * Click **Save**.  
   * Click **Write**.  
3. **Boot the Pi:**  
   * Eject the SD card and put it in the Pi.  
   * Connect the Pi to your mom's router with an **Ethernet cable**. This is its permanent internet connection.  
   * Connect the power.  
4. **Log in (via Terminal):**  
   * Wait 2-3 minutes.  
   * On your Mac, open the **Terminal** app.  
   * Log into the Pi via SSH (use the hostname you set):  
     ssh pi@greenhouse-pi.local

   * Enter the password you created in the imager.  
5. **Install Docker:** Docker is the software that runs containers.  
   curl \-fsSL \[https://get.docker.com\](https://get.docker.com) \-o get-docker.sh  
   sudo sh get-docker.sh  
   sudo usermod \-aG docker pi

   *After this, **log out (exit) and log back in** for the changes to take effect.*

## **3\. Configure the isolated IoT network**

This is where we turn the Pi's built-in WiFi into its own private network.

1. **Log in** to your Pi via SSH.  
2. **Install networking tools:**  
   sudo apt update  
   sudo apt install hostapd dnsmasq

3. **Configure hostapd** (the Access Point software):  
   * Create a new configuration file:  
     sudo nano /etc/hostapd/hostapd.conf

   * Paste this *exact* content into the file. Choose a secure password.  
     interface=wlan0  
     driver=nl80211  
     ssid=GREENHOUSE\_IOT  
     hw\_mode=g  
     channel=7  
     wmm\_enabled=0  
     macaddr\_acl=0  
     auth\_algs=1  
     ignore\_broadcast\_ssid=0  
     wpa=2  
     wpa\_passphrase=YourSecurePassword  
     wpa\_key\_mgmt=WPA-PSK  
     wpa\_pairwise=TKIP  
     rsn\_pairwise=CCMP

   * Save and exit (Ctrl+O, Enter, Ctrl+X).  
4. **Configure dnsmasq** (the DHCP/DNS server):  
   * Edit the main configuration file:  
     sudo nano /etc/dnsmasq.conf

   * Paste this at the *end* of the file:  
     interface=wlan0  
     dhcp-range=10.0.0.50,10.0.0.150,255.255.255.0,12h

   * Save and exit.  
5. **Set a static IP for the Pi's WiFi:**  
   * Edit the dhcpcd.conf file:  
     sudo nano /etc/dhcpcd.conf

   * Paste this at the *end* of the file:  
     interface wlan0  
     static ip\_address=10.0.0.1/24  
     nohook wpa\_supplicant

   * Save and exit.  
6. **Start the new network:**  
   * Reboot the Pi: sudo reboot  
   * After it reboots, log back in. Your GREENHOUSE\_IOT WiFi network should now be visible from your phone or Mac (but don't connect to it).

## **4\. Install Home Assistant**

1. **Log in** to your Pi via SSH.  
2. **Run the Home Assistant container:** This command is a one-time copy-paste. It tells Docker to run Home Assistant, give it access to your configuration files, and restart it automatically.  
   docker run \-d \\  
     \--name homeassistant \\  
     \--privileged \\  
     \--restart=unless-stopped \\  
     \-e TZ=America/New\_York \\  
     \-v /home/pi/ha\_config:/config \\  
     \--network=host \\  
     ghcr.io/home-assistant/home-assistant:stable

   *(Note: TZ is set to America/New\_York for the Outer Banks; adjust if needed).*  
3. **Onboard:**  
   * Wait 5-10 minutes for the first boot.  
   * On your Mac, go to: http://greenhouse-pi.local:8123  
   * You will see the "Welcome" screen. Create your account.

## **5\. Install ESPHome**

ESPHome will also run as a separate container.

1. **Log in** to your Pi via SSH.  
2. **Run the ESPHome container:**  
   docker run \-d \\  
     \--name esphome \\  
     \--restart=unless-stopped \\  
     \-v /home/pi/esphome\_config:/config \\  
     \-p 6052:6052 \\  
     \--network=host \\  
     ghcr.io/esphome/esphome:stable

3. **Access ESPHome:** The ESPHome dashboard will now be running on a different port. Go to: http://greenhouse-pi.local:6052

## **6\. Build and program your first sensor**

This is the prototype test. You will wire the BME280 sensor to the ESP32 and use ESPHome to program it.

### **6.a. Hardware assembly (the wiring)**

Use your breadboard and jumper wires to connect the sensor. The BME280 sensor uses the I2C communication protocol, which requires four wires.

* **ESP32 3.3V** \-\> BME280 **VIN** (Power)  
* **ESP32 GND** \-\> BME280 **GND** (Ground)  
* **ESP32 GPIO 22** \-\> BME280 **SCL** (Clock)  
* **ESP32 GPIO 21** \-\> BME280 **SDA** (Data)

### **6.b. Software (the YAML)**

1. Go to the **ESPHome dashboard** at http://greenhouse-pi.local:6052.  
2. Click the **\+ New device** button.  
3. Follow the wizard. Give it a name like greenhouse\_node\_1.  
4. When it asks for your WiFi details, enter the credentials for the **new, isolated network you just created**:  
   * **SSID:** GREENHOUSE\_IOT  
   * **Password:** YourSecurePassword  
5. Select **ESP32** as the device type.  
6. Click **Edit** on the new node.  
7. Paste this code at the *end* of the YAML file (the esphome:, wifi:, and api: sections should already be there).  
   \# ... (existing esphome, wifi, api sections) ...

   \# Enable the I2C bus on the default pins  
   i2c:  
     sda: 21  
     scl: 22  
     scan: true

   \# Define the sensor attached to the I2C bus  
   sensor:  
     \- platform: bme280  
       name: "Greenhouse Temperature"  
       temperature:  
         oversampling: 16x  
       pressure:  
         oversampling: 16x  
       humidity:  
         oversampling: 16x  
       update\_interval: 30s

8. Click **Save**.

### **6.c. Flashing (programming the chip)**

1. Connect your wired-up ESP32 to your Mac using a USB cable.  
2. In the ESPHome UI (http://greenhouse-pi.local:6052), click **Install** on your new node.  
3. Select **Plug into this computer**.  
4. A new window will pop up. Select the USB port your ESP32 is connected to (it may be named CP210x or similar) and click **Connect**.  
5. ESPHome will compile the code and flash it to the ESP32. This may take a few minutes.  
6. Once done, disconnect the ESP32 from your Mac and power it with a USB charger. It will automatically connect to your Pi's GREENHOUSE\_IOT network.

## **7\. The result (see your data)**

1. Go to your **Home Assistant dashboard** (http://greenhouse-pi.local:8123).  
2. Go to **Settings** \> **Devices & services**.  
3. ESPHome will have automatically discovered the new device on the network. Click **Configure**.  
4. Add the device. Your "Greenhouse Temperature" sensor is now in Home Assistant.