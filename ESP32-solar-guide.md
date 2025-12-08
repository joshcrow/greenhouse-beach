# Weather Station Build Guide: ESP32-E + BME280 + Solar

## 1. Bill of Materials
*   **Controller:** FireBeetle 2 ESP32-E (DFR0654 / 1738-DFR0654-F-ND)
*   **Battery:** Li-Ion 3.7V 2.5Ah (DigiKey: 1528-1840-ND)
*   **Enclosure:** Gray Box 4.53" x 2.56" (DigiKey: 377-1879-ND)
*   **Cable Glands:** PG7 2-5mm (DigiKey: RPC3638-ND)
*   **Sensor:** BME280 (I2C Pressure/Humidity/Temp)
*   **Power:** Eujgoov 6V 1W Solar Panel (Amazon Listing)

---

## 2. Board Preparation (Soldering)
**Objective:** Solder wires to the **BOTTOM (flat)** side of the FireBeetle to ensure the lid closes easily.

**1. Solar Panel Input:**
*   Locate the two large gold square pads at the bottom edge (near the USB port).
*   **Solar Red (+):** Solder to the pad labeled **VIN** (Bottom Right).
*   **Solar Black (-):** Solder to the pad labeled **GND** (Bottom Left).
*   *Note:* No blocking diode is strictly required for this 1W panel with this board, but if you have a Schottky diode (e.g., 1N5817), place it on the Red wire (Band towards board).

**2. BME280 Sensor:**
*   Solder directly to the pins sticking out on the right edge (looking at the bottom).
*   **Sensor VCC:** Solder to **3V3** (4th pin up from bottom right).
*   **Sensor GND:** Solder to **GND** (3rd pin up from bottom right).
*   **Sensor SCL:** Solder to **SCL** (2nd pin up from bottom right).
*   **Sensor SDA:** Solder to **SDA** (1st pin up from bottom right).

**3. "Low Power" Mod:**
*   **Action:** **NONE.**
*   *Reason:* Your specific board (ESP32-E V1.0) does not have the power-draining "vampire" LED found on C6 models. The blue LED is controlled by Pin D9—just ensure your code keeps D9 LOW during sleep.

---

## 3. Enclosure Preparation
**Objective:** Create a waterproof housing with two distinct entry points.

1.  **Drill Holes:**
    *   Drill two **12.5mm (0.5")** holes in the bottom face of the gray box.
    *   Space them ~1 inch apart to allow room for tightening.
2.  **Install Glands:**
    *   Insert the PG7 glands.
    *   Tighten the internal locking nut firmly.
    *   Leave the external dome caps loose.

---

## 4. Final Assembly
**Objective:** Fit components without crushing wires or overheating.

1.  **Routing:**
    *   Pass the **Solar Panel** cable through Gland #1.
    *   Pass the **Sensor** cable through Gland #2.
2.  **Battery Placement (The Tight Fit):**
    *   **Action:** Rotate the battery 90 degrees. It will fit lengthwise in the box.
    *   Secure it to the "floor" of the box with double-sided foam tape.
3.  **Stacking:**
    *   Place a small piece of foam or electrical tape on top of the battery to prevent shorts.
    *   Rest the ESP32 (flat side up/components down) on top of the battery.
4.  **Connection:**
    *   Plug the battery JST connector into the white port on the ESP32.
5.  **Sealing:**
    *   Tighten the external gland caps around the wires.
    *   Screw the lid shut.

---

## 5. Mounting & Deployment
*   **Solar Panel:** Mount facing South (Northern Hemisphere) at ~45° tilt.
*   **The Box:** **MUST BE SHADED.** Mount the gray box behind the solar panel or under an overhang. Direct sun on the box will overheat the Li-Ion battery (>60°C is dangerous).
*   **Sensor:** Mount the BME280 inside your external radiation shield.

## 6. Code Configuration
To ensure reliability with the wire run to the sensor:

```cpp
void setup() {
  // Initialize I2C with lower clock speed for wire reliability
  Wire.begin();
  Wire.setClock(10000); // 10kHz clock speed

  // Ensure onboard LED is off
  pinMode(D9, OUTPUT);
  digitalWrite(D9, LOW); 
  
  // Your BME280 setup code here...
}