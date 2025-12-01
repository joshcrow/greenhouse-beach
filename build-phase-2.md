# **Build guide 02: Adding soil, light sensors, and camera**

## **Objective**

This guide follows "Build Guide: Pi Setup and First Sensor." The goal is to complete the hardware assembly for Phase 1 by adding the capacitive soil moisture and ambient light sensors to the existing ESP32 node. It also covers the physical installation and software configuration of the Raspberry Pi camera.

**Prerequisites:**  
* Complete all steps from "Build Guide: Pi Setup and First Sensor"  
* Verify your ESP32 node (greenhouse\_node\_1) is online and reporting data in Home Assistant  
* Verify your Pi is accessible and Home Assistant is running

**Estimated time:** 1-2 hours

## **1\. Required hardware**

Components from the previous guide are required, plus the remaining items from the Phase 1 Bill of Materials:

* 1x Capacitive soil moisture sensor (v1.2 or similar)  
* 1x BH1750 ambient light sensor  
* 1x Raspberry Pi Camera Module 3 (or a compatible USB webcam)  
* Additional jumper wires (M-F, F-F)

## **2\. Part 1: Add light and soil sensors to the ESP32**

The new sensors will be added to the greenhouse\_node\_1 ESP32.

### **2.a. Hardware assembly (the wiring)**

First, **unplug the ESP32 from its 5V power source.**  
The **BH1750** (light sensor) also uses the I2C protocol, just like the BME280. This means it can **share the same four pins** on the breadboard.

1. **Wire the BH1750:**  
   * Connect the BH1750's **VIN** pin to the **same breadboard rail** as the BME280's VIN (which is connected to **ESP32 3.3V**).  
   * Connect the BH1750's **GND** pin to the **same breadboard rail** as the BME280's GND (which is connected to **ESP32 GND**).  
   * Connect the BH1750's **SCL** pin to the **same breadboard rail** as the BME280's SCL (which is connected to **ESP32 GPIO 22**).  
   * Connect the BH1750's **SDA** pin to the **same breadboard rail** as the BME280's SDA (which is connected to **ESP32 GPIO 21**).

The **Capacitive Soil Moisture Sensor** is an analog sensor, so it needs its own dedicated "Analog" pin.

2. **Wire the Soil Sensor:** This sensor has three pins:  
   * Connect the sensor's **VCC** pin to the **ESP32 3.3V** breadboard rail.  
   * Connect the sensor's **GND** pin to the **ESP32 GND** breadboard rail.  
   * Connect the sensor's **AOUT** (Analog Out) pin to **ESP32 GPIO 34**. (This is a common analog-input pin).

### **2.b. Software (the YAML)**

1. Go to the **ESPHome dashboard** at http://greenhouse-pi.local:6052.  
2. Click **Edit** on the greenhouse\_node\_1 device.  
3. Add the new sensor configurations to the *end* of the sensor: block. The i2c: block should remain unchanged.  
   The *entire* sensor: block should now look like this:  
   \# ... (existing esphome, wifi, api, i2c sections) ...

   sensor:  
     \# BME280 (from previous guide)  
     \- platform: bme280  
       name: "Greenhouse Temperature"  
       temperature:  
         oversampling: 16x  
       pressure:  
         oversampling: 16x  
       humidity:  
         oversampling: 16x  
       update\_interval: 30s

     \# NEW: BH1750 (Ambient Light)  
     \- platform: bh1750  
       name: "Greenhouse Ambient Light"  
       address: 0x23 \# This is the default address, 0x5C is the other option  
       update\_interval: 30s

     \# NEW: Capacitive Soil Moisture  
     \- platform: adc  
       pin: GPIO34  
       name: "Greenhouse Soil Moisture"  
       attenuation: 11db  
       update\_interval: 30s  
       unit\_of\_measurement: "%"  
       filters:  
         \- lambda: return (x / 4095.0) * 100.0;  
         \- calibrate\_linear:  
             \- 0.0 \-\> 0  
             \- 1.0 \-\> 100

4. Click **Save**.

### **2.c. Flashing (Over-The-Air)**

Since the ESP32 is already powered on and connected to the private GREENHOUSE\_IOT network, it does not need to be plugged into the Mac.

1. **Plug the ESP32 back into its 5V power adapter.** Wait one minute for it to boot and reconnect to the GREENHOUSE\_IOT network.  
2. On the ESPHome dashboard, the greenhouse\_node\_1 should appear as **Online**.  
3. Click **Install**.  
4. Select **Wirelessly**.  
5. ESPHome will compile the new configuration and send it to the ESP32 over the WiFi network. The device will reboot.

After it reboots, Home Assistant will automatically discover the new entities ("Greenhouse Ambient Light" and "Greenhouse Soil Moisture"). The BME280 "Pressure" sensor should already be visible from the previous guide.

**Note:** The soil moisture sensor reading will need calibration. The current configuration maps the raw ADC value (0-4095) to a percentage (0-100%). You may need to adjust the calibration values based on your specific sensor and soil type. Dry soil typically reads higher values, while wet soil reads lower values.

## **3\. Part 2: Install the camera**

This part involves configuring the Raspberry Pi itself.

1. **Power down the Pi:** Log into the Pi via SSH and run sudo poweroff. Unplug the power.  
2. **Physically install the camera:**  
   * Gently open the camera connector on the Pi board.  
   * Insert the Pi Camera Module's ribbon cable (ensure the blue-taped side faces the Ethernet/USB ports).  
   * Gently push the connector clip back in to secure the cable.  
3. **Boot the Pi** and log in via SSH.  
4. **Enable the camera:**  
   * Run the configuration tool: sudo raspi-config  
   * Navigate to **Interface Options**.  
   * Navigate to **Camera** (or **Legacy Camera** on older Pi OS versions) and select **\<Yes\>** to enable it.  
   * Select **\<Finish\>** and **\<Yes\>** to reboot the Pi.  
   * After reboot, verify the camera is detected: `vcgencmd get_camera` (should show `supported=1 detected=1`)  
5. **Add the camera to Home Assistant:**  
   * Go to the **Home Assistant dashboard** (http://greenhouse-pi.local:8123).  
   * Go to **Settings** \> **Devices & services**.  
   * Click **\+ Add integration**.  
   * Search for and select **Raspberry Pi Camera**.  
   * The default settings should work. Click **Submit**.

A camera.raspberry\_pi\_camera entity will now be available in Home Assistant.

## **4\. Part 3: Basic dashboard visualization**

This is the first step of the **UI/UX design workflow (Section 3\)** from the project plan.

1. In Home Assistant, go to the main **Overview** dashboard.  
2. Click the **three-dot menu** (top right) and select **Edit dashboard**.  
3. Click the **\+ Add card** button in the bottom right.  
4. Add cards for the new sensors:  
   * **Light:** Find the **Gauge** card. Select sensor.greenhouse\_ambient\_light as the entity.  
   * **Soil Moisture:** Find the **Gauge** card. Select sensor.greenhouse\_soil\_moisture as the entity.  
   * **Camera:** Find the **Picture Glance** card. Select camera.raspberry\_pi\_camera as the camera entity.  
5. Click **Save**.

A basic dashboard is now configured showing all Phase 1 data: temperature, humidity, pressure, light, soil moisture, and a live camera feed.

**Verification:**  
* Check that all sensors are reporting data in Home Assistant  
* Verify the camera feed is displaying correctly  
* Test sensor values by moving the light sensor or changing soil moisture to confirm readings update

## **5\. Troubleshooting**

### **Sensor issues:**
* **BH1750 (light sensor) not detected:**  
  * Verify I2C wiring is correct (shares same I2C bus as BME280)  
  * Check I2C address in ESPHome logs (should show 0x23 or 0x5C)  
  * Try changing the address in the YAML from 0x23 to 0x5C

* **Soil moisture sensor reading 0% or 100% constantly:**  
  * Verify wiring (especially the analog pin connection)  
  * Check sensor is powered (3.3V, not 5V)  
  * Calibration may be needed - the sensor may need different calibration values based on your soil type  
  * Test sensor in air (should read dry) and in water (should read wet)

* **Sensors not appearing in Home Assistant after OTA update:**  
  * Wait 1-2 minutes for Home Assistant to discover new entities  
  * Check ESPHome dashboard shows device as "Online"  
  * Try restarting Home Assistant: `docker restart homeassistant`

### **Camera issues:**
* **Camera not detected:**  
  * Verify camera connector is properly seated (check both ends if using ribbon cable extension)  
  * Check camera is enabled: `sudo raspi-config` \> Interface Options \> Camera  
  * Verify camera detection: `vcgencmd get_camera`  
  * Check camera module is compatible with your Pi model

* **Camera not appearing in Home Assistant:**  
  * Verify the Raspberry Pi Camera integration is installed  
  * Check Home Assistant logs for camera errors: Settings \> System \> Logs  
  * Try restarting Home Assistant: `docker restart homeassistant`

* **Camera feed is black or not updating:**  
  * Verify camera is not blocked or covered  
  * Check camera permissions in Home Assistant  
  * Try accessing camera directly via SSH: `raspistill -o test.jpg`

### **Network/OTA update issues:**
* **OTA update fails:**  
  * Verify ESP32 is connected to GREENHOUSE\_IOT network  
  * Check ESP32 has sufficient power (may need higher current USB adapter)  
  * Try wired update first to verify configuration is correct  
  * Ensure ESP32 is within WiFi range of the Pi