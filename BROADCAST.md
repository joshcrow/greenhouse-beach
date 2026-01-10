# 📢 BROADCAST - January 10, 2026

## 🔴 Interior Temperature Sensor Offline

**Status:** sensor1 ESP32 @ 10.0.0.88 is unreachable (100% packet loss)  
**Duration:** Offline since ~January 4, 2026 (6 days)  
**Impact:** Interior greenhouse temperature stuck at 60.8°F in charts and emails

### Symptoms
- `sensor.sensor1_greenhouse_temperature` in Home Assistant shows "unavailable"
- The persistent template sensor holds the last known value (60.8°F)
- Chart "Inside" line is flatlined; "Outside" line is working correctly

### Hardware Details
| Property | Value |
|----------|-------|
| **Device** | ESP32 (esp32dev) |
| **Sensor** | BME280 on I2C (SDA:21, SCL:22, addr: 0x76) |
| **Network** | GREENHOUSE_IOT WiFi |
| **Expected IP** | 10.0.0.88 |
| **Power** | Should be powered via greenhouse-pi battery system |

### Root Cause Hypothesis
The ESP32 has either:
1. Lost WiFi connection and failed to reconnect
2. Firmware crashed and needs power cycle
3. Lost power (cable disconnected or battery issue)

---

## 🛠️ Action Required

**@Nick** — When you're back on Monday, please investigate at Mom's greenhouse:

1. **Locate the sensor1 ESP32** (should be near the greenhouse-pi, connected to same battery)
2. **Check if it's powered** — LED should be on
3. **Power cycle it** — Unplug for 10 seconds, reconnect
4. **Verify it comes back online:**
   ```bash
   ssh joshcrow@greenhouse-pi "ping -c 3 10.0.0.88"
   ```

Once online, HA will auto-reconnect and the chart will start showing interior temperature variation again.

---

## ✅ Other Fixes Deployed (Jan 10)

- **Chart Outside flatline** — Fixed! Now correctly shows 55-69°F variation
- **Wind arrow direction** — Fixed! Now points where wind is blowing (Apple Weather style)
- **Sound water level physics** — Updated narrator prompt with correct Albemarle bathtub rules

---

*Last updated: January 10, 2026 @ 11:22 AM EST*
