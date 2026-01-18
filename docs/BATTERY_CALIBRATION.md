# Satellite-2 Battery Voltage Calibration Issue

## Problem
The satellite-2 sensor reports **3.98V** but stopped transmitting, indicating the actual battery voltage is much lower (likely <3.0V). The ESP32 ADC reading is inaccurate.

## Root Cause
1. **ESPHome config multiplies ADC reading by 2.0** (line 170 in `satellite-sensor-2.yaml`)
2. **Voltage divider may not be exactly 1:2** due to resistor tolerances
3. **ESP32 ADC has ±10% accuracy** without calibration

## Evidence
- Last battery reading: **3.98V** (Dec 23, 2025 at 10:21 PM)
- Sensor stopped transmitting immediately after
- Battery readings were stuck at exactly 3.98V for the last hour
- 100+ hours offline (sensor is dead)

## Immediate Action Required
**Charge or replace the battery NOW.** The sensor has been offline for 4+ days.

## Calibration Steps (After Charging)

### 1. Measure Actual Battery Voltage
Use a multimeter to measure the actual LiPo battery voltage:
- **Fully charged**: Should read ~4.2V
- **Nominal**: ~3.7V
- **Low**: ~3.4V
- **Dead**: <3.0V

### 2. Compare to ESPHome Reading
Enable maintenance mode to keep sensor awake:
```bash
# Via MQTT
mosquitto_pub -h 10.0.0.1 -u greenhouse -P <password> \
  -t "greenhouse/satellite-2/maintenance/state" -m "ON"
```

Check the reported voltage in Home Assistant or MQTT.

### 3. Calculate Calibration Factor
```
Calibration Factor = Actual Voltage / Reported Voltage
```

Example:
- Actual voltage: 4.15V (measured with multimeter)
- Reported voltage: 3.98V (from ESPHome)
- Calibration factor: 4.15 / 3.98 = **1.043**

### 4. Update ESPHome Config
Edit `esphome/sensors/satellite-sensor-2.yaml` line 170:

**Before:**
```yaml
filters:
  - multiply: 2.0  # FireBeetle has 1/2 voltage divider
```

**After:**
```yaml
filters:
  - multiply: 2.086  # Calibrated: 2.0 * 1.043 = 2.086
```

### 5. Reflash and Test
```bash
cd esphome
esphome run sensors/satellite-sensor-2.yaml
```

## Better Solution: Use Calibrate Linear Filter

For more accurate readings across the voltage range:

```yaml
sensor:
  - platform: adc
    pin: 34
    id: battery_voltage
    name: "Satellite 2 Battery"
    update_interval: never
    attenuation: 11db
    filters:
      - multiply: 2.0  # Initial voltage divider compensation
      - calibrate_linear:
          # Measure at two points: low battery and full battery
          - 3.0 -> 3.0   # When multimeter reads 3.0V, ESPHome should show 3.0V
          - 4.2 -> 4.2   # When multimeter reads 4.2V, ESPHome should show 4.2V
```

## Monitoring Recommendations

Add battery alerts to prevent future outages:

```yaml
# In satellite-sensor-2.yaml, add to binary_sensor section:
binary_sensor:
  - platform: template
    name: "Satellite 2 Battery Low"
    lambda: |-
      return id(battery_voltage).state < 3.4;
```

Then configure Home Assistant to send alerts when battery is low.

## Current Status (Dec 27, 2025)
- ❌ Sensor offline for 100+ hours
- ❌ Last reading: 3.98V (likely inaccurate)
- ❌ Actual battery voltage: Unknown (likely <3.0V - DEAD)
- ⚠️ **ACTION REQUIRED**: Charge battery immediately
