# **Build guide 02: Adding soil, light sensors, and camera**

## **Objective**

This guide follows "Build Guide: Pi Setup and First Sensor." The goal is to complete the hardware assembly for Phase 1 by adding the capacitive soil moisture and ambient light sensors to the existing ESP32 node. It also covers the physical installation and software configuration of the Raspberry Pi camera.

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

4. Click **Save**.

### **2.c. Flashing (Over-The-Air)**

Since the ESP32 is already powered on and connected to the private GREENHOUSE\_IOT network, it does not need to be plugged into the Mac.

1. **Plug the ESP32 back into its 5V power adapter.** Wait one minute for it to boot and reconnect to the GREENHOUSE\_IOT network.  
2. On the ESPHome dashboard, the greenhouse\_node\_1 should appear as **Online**.  
3. Click **Install**.  
4. Select **Wirelessly**.  
5. ESPHome will compile the new configuration and send it to the ESP32 over the WiFi network. The device will reboot.

After it reboots, Home Assistant will automatically discover the three new entities ("Greenhouse Ambient Light," "Greenhouse Soil Moisture," and the BME280 "Pressure" sensor).

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
   * Navigate to **Legacy Camera** and select **\<Yes\>** to enable it.  
   * Select **\<Finish\>** and **\<Yes\>** to reboot the Pi.  
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