# **Remote greenhouse monitoring and automation project plan**

## **Project overview**

This plan outlines the development of an "offline-first" environmental monitoring and control system for a remote greenhouse. The project leverages existing UI/UX design and CADD/3D printing skills to build a robust, open-source IoT solution.  
**Location context:** The greenhouse is situated in the Outer Banks, NC, with intermittent internet connectivity due to weather. **All essential monitoring and control functions must operate independently on the local network.**

## **1\. Core technology architecture**

This stack is selected for local operational reliability, open-source flexibility, and minimized reliance on extensive programming expertise.

| Component | Recommendation | Role | Rationale |
| :---- | :---- | :---- | :---- |
| **Controller** | **Raspberry Pi 4 or 5** | Hosts the centralized operating system, data storage, and dashboard application. | Provides necessary processing power for future AI integration (Phase 3). |
| **Operating system** | **Raspberry Pi OS (Lite) \+ Home Assistant Container** | Runs the core server application within a container on a standard OS. | Provides host OS access to configure the Pi as an isolated WiFi Access Point (AP), ensuring all IoT devices are on a stable, private network. |
| **Network arch.** | **Isolated IoT network** | Pi acts as WiFi AP (via hostapd) and DHCP server (via dnsmasq). | Creates a private GREENHOUSE\_IOT network for all ESP32s. Decouples the system from the home router. Prevents failure if the home WiFi password changes or router reboots. |
| **Sensor nodes** | **ESP32 / ESP8266** | Low-power, wireless microcontrollers for remote data collection. | Connects directly to the Pi's private WiFi network. |
| **Node firmware** | **ESPHome** | Configuration management tool for ESP nodes. | Permits device programming via YAML configuration files, minimizing the need for C/C++ development. |
| **User interface** | **Figma design \+ Home Assistant Lovelace** | Dashboard design completed in Figma and implemented using Home Assistant's native custom card system. | Maximizes the use of design skills while reducing the need for full-stack web development. |
| **Enclosures** | **OnShape / STL Files** | Used to design and 3D print custom, weatherproof housings for all electronic components. | Utilizes CADD skills to ensure component protection and proper mounting. |

## **2\. Project phases and objectives**

### **Phase 1: Monitoring (MVP)**

**Objective:** Establish core hardware, local data acquisition, and remote visual access.

| Task Category | Deliverables | Key Components / Focus |
| :---- | :---- | :---- |
| **Hardware setup** | Installation of the Pi controller and one foundational ESP32 sensor node. | **Sensors:** BME280 (temperature/humidity), Capacitive soil moisture, BH1750 (light). |
| **Networking** | **Pi configured as a WiFi Access Point.** Home Assistant and ESPHome operational. | **Verification:** Pi hosts a private GREENHOUSE\_IOT network. ESP32s connect to this network, not the home WiFi. Pi connects to home internet via Ethernet. |
| **Data visualization** | Creation of historical time-series charts for all collected sensor data. | **Figma:** Development of the "Monitoring view" wireframes. |
| **Visual capture** | Configuration of live video streaming and automatic scheduled daily timelapse capture. | **Camera:** Raspberry Pi Camera Module 3 or a suitable USB webcam. |
| **Remote access** | Implementation of secure external access for remote monitoring. | **Security:** Use of Nabu Casa or manual setup (DuckDNS, NGINX) for encrypted tunnel (HTTPS). |

### **Phase 2: Automation**

**Objective:** Integrate control hardware and implement essential local control loops for environmental management.

| Task Category | Deliverables | Key Components / Focus |
| :---- | :---- | :---- |
| **Hardware integration** | Installation of a relay board and primary actuators (fan, pump). | **Actuators:** Relay Module (5V/12V), 12V DC water pump, Smart Plug (flashed with local firmware like Tasmota/ESPHome). |
| **Control logic** | Deployment of three core automation routines within Home Assistant. | **Examples:** 1\. Temperature threshold fan control. 2\. Soil moisture content irrigation control. 3\. Scheduled lighting based on ambient light levels. |
| **Irrigation** | Installation of a simple drip irrigation system connected to the main water pump relay. | **CADD:** Design 3D-printed mounting brackets for all weatherproof actuator enclosures. |
| **Interface control** | Addition of manual control switches and scheduling inputs to the Home Assistant Lovelace dashboard. | **Figma:** Design of the "Control panel" and "Automation status" interface elements. |

### **Phase 3: AI and expansion**

**Objective:** Achieve system resilience, expand external monitoring, and integrate AI for data insights.

| Task Category | Deliverables | Key Components / Focus |
| :---- | :---- | :---- |
| **Resilience/water** | Integration of battery backup monitoring; rain barrel water level sensing. | **Hardware:** Ultrasonic sensor (for water level), necessary DC-to-DC voltage converters. |
| **External monitoring** | Deployment of a second ESP32 node for outside atmospheric conditions. | **Sensors:** External BME280 or equivalent (Temp/Hum/Pressure) for indoor-outdoor data comparison. |
| **AI vision** | **Pest/intruder detection:** Implementation of a computer vision system for object recognition using the camera feed. | **Software:** Installation of Frigate NVR (Optional: Google Coral USB Accelerator to handle processing load). |
| **AI health** | Implementation of an experimental automation to analyze high-resolution plant photos. | **Learning:** Exploration of Python/TensorFlow Lite for local plant disease detection or growth analysis. |
| **Interface reporting** | Development of a dedicated "Health report" dashboard view. | **Figma:** Design of the "Analytics/AI insight" data visualization panel. |

## **3\. UI/UX design workflow**

The user interface will be designed in Figma and implemented in Home Assistant. The workflow is as follows:

1. **Design (Figma):** Create high-fidelity mockups of the dashboard (monitoring, control, and reporting views). Define layout, typography, and color palettes.  
2. **Deconstruct:** Analyze the Figma design and identify which Home Assistant (Lovelace) cards can be used to replicate the design (e.g., gauge-card, history-graph-card, button-card).  
3. **Identify Gaps:** For UI elements in Figma that have no standard Lovelace card, search for custom cards in the Home Assistant Community Store (HACS). The button-card is highly customizable and can replicate complex UI.  
4. **Theme:** Use Home Assistant themes to apply the custom color palette and fonts defined in Figma to the entire dashboard.

## **4\. Project tracking and documentation**

* **Version control:** A GitHub repository will be used as the central "source of truth" for this project plan and all future configuration files (e.g., ESPHome YAML, Home Assistant automations).  
* **Documentation:** The project\_plan.md (this file) will serve as the living README.md file in the repository.  
* **Workflow:** All changes will be saved using the standard git add \-\> git commit \-\> git push workflow.

## **5\. Phase 1: Bill of materials (MVP)**

This list covers the essential hardware required to complete Phase 1\.

* **Controller:**  
  * 1x Raspberry Pi 4 (4GB+ model) or Raspberry Pi 5  
  * 1x 32GB (or larger) A2-rated microSD card  
  * 1x Official Raspberry Pi USB-C power supply  
* **Sensor node:**  
  * 1x ESP32-WROOM-32 development board (with USB)  
  * 1x Breadboard (for prototyping)  
  * 1x Jumper wire kit (M-M, M-F, F-F)  
* **Sensors (MVP):**  
  * 1x BME280 sensor (temperature, humidity, pressure)  
  * 1x Capacitive soil moisture sensor (v1.2 or similar)  
  * 1x BH1750 ambient light sensor  
* **Visuals:**  
  * 1x Raspberry Pi Camera Module 3 (or a compatible USB webcam)  
* **Enclosures:**  
  * Access to a 3D printer and filament (PETG recommended for heat/UV resistance over PLA)

## **6\. Initial setup steps**

1. **Procurement:** Order the hardware specified in the Phase 1 Bill of Materials.  
2. **Configuration:** Flash the SD card with **Raspberry Pi OS (Lite)** and install Home Assistant Container.  
3. **Networking:** Configure the Pi's host OS to act as a WiFi Access Point (hostapd) and DHCP server (dnsmasq).  
4. **Software prep:** Install the **ESPHome** add-on within the Home Assistant environment.  
5. **Prototype test:** Assemble the BME280 sensor and ESP32 on a breadboard. Compile and flash the configuration to connect to the Pi's private WiFi network. Confirm successful data transmission.