# Greenhouse Gazette Admin Guide

Quick reference for common admin tasks. All commands run from the `greenhouse-beach` directory.

---

## 📧 Email Operations

### Send Test Email
```bash
docker compose exec storyteller python scripts/publisher.py --test
```
Sends a full test email to the test recipient (single address).

### Send Production Email
```bash
docker compose exec storyteller python scripts/publisher.py
```
Sends to all subscribers. **Use with caution.**

### Preview Email Templates (Hot Reload)
```bash
docker compose exec storyteller python scripts/email_preview.py
```
Then visit: **http://localhost:8081/**

Templates reload on every request - edit and refresh to see changes.

| Route | Description |
|-------|-------------|
| `/` | Normal daily email |
| `/?mode=weekly` | Weekly edition |
| `/?mode=stale` | Stale sensor warning |
| `/?mode=alert` | Alert mode |

---

## 💬 Narrative Injection (One-Time Messages)

Add a special message to the next email (birthdays, announcements, etc.):

```bash
cat > data/narrative_injection.json << 'EOF'
{
  "message": "Your message here - AI will weave it into the narrative",
  "queued_at": "2026-01-06T00:00:00Z"
}
EOF
```

**Note:** The injection is automatically deleted after use. You must recreate it after each test email.

### Check Current Injection
```bash
cat data/narrative_injection.json
```

---

## 📢 Broadcast Messages

### Create a Broadcast
```bash
echo '{"title": "Important Update", "message": "Your broadcast text"}' > data/broadcast.json
```

### Quick Broadcast Test
```bash
./scripts/test_broadcast.sh "Your message here"
```

### Poll Inbox for Broadcasts
```bash
./scripts/test_broadcast.sh --poll-only
```

---

## 📊 Data & Status

### View Current Sensor Status
```bash
cat data/status.json | python3 -m json.tool
```

### View 24h Statistics
```bash
cat data/stats_24h.json | python3 -m json.tool
```

### View Sensor Logs
```bash
# Recent entries
tail -20 data/sensor_log/2026-01.jsonl | python3 -m json.tool

# Search for specific data
grep "interior_temp" data/sensor_log/2026-01.jsonl | tail -5
```

### View Narrative History
```bash
cat data/narrative_history.json | python3 -m json.tool
```

### View Riddle State
```bash
cat data/riddle_state.json | python3 -m json.tool
```

---

## 🔧 Container Management

### Rebuild After Code Changes
```bash
docker compose build storyteller
docker compose down storyteller && docker compose up -d storyteller
```

### View Logs
```bash
docker compose logs -f storyteller
```

### Check Container Status
```bash
docker compose ps
```

### Restart All Services
```bash
docker compose down && docker compose up -d
```

---

## 🤖 AI Model Configuration

### Current Model
```bash
grep GEMINI_MODEL .env
```

### Change Model
Edit `.env`:
```bash
GEMINI_MODEL=gemini-3-pro-preview    # Best reasoning (current)
GEMINI_MODEL=gemini-3-flash-preview  # Faster, cheaper
GEMINI_MODEL=gemini-2.5-flash        # Stable fallback
```

Then rebuild:
```bash
docker compose build storyteller && docker compose down storyteller && docker compose up -d storyteller
```

### List Available Models
```bash
docker compose exec storyteller python scripts/narrator.py
```

---

## 📸 Timelapse & Camera

### Generate Daily Timelapse
```bash
docker compose exec storyteller python scripts/timelapse.py
```

### Generate Extended Timelapse (7 days)
```bash
docker compose exec storyteller python scripts/extended_timelapse.py
```

### View Camera Images
```bash
ls -la data/camera/2026/01/
```

---

## 📈 Charts

### Generate 24h Weather Chart
```bash
docker compose exec storyteller python -c "
import sys; sys.path.insert(0, '/app/scripts')
from chart_generator import generate_weather_dashboard
png = generate_weather_dashboard(24)
print(f'Generated: {len(png)} bytes')
"
```

### Generate Weekly Chart (168h)
```bash
docker compose exec storyteller python -c "
import sys; sys.path.insert(0, '/app/scripts')
from chart_generator import generate_weather_dashboard
png = generate_weather_dashboard(168)
with open('/tmp/weekly_chart.png', 'wb') as f: f.write(png)
print('Saved to /tmp/weekly_chart.png')
"
```

---

## 🌊 External Data Services

### Refresh Coast/Sky Data
```bash
docker compose exec storyteller python scripts/coast_sky_service.py
```

### Check Tide Cache
```bash
cat data/coast_sky_cache.json | python3 -m json.tool
```

---

## 🔐 Configuration Files

| File | Purpose |
|------|---------|
| `.env` | API keys, SMTP credentials, model config |
| `configs/registry.json` | Sensor definitions, MQTT mappings |
| `templates/daily_email.html` | Email template (Jinja2) |
| `templates/weekly_email.html` | Weekly edition template |

---

## 🐛 Troubleshooting

### Check MQTT Connection
```bash
docker compose exec storyteller python -c "
import paho.mqtt.client as mqtt
import os
client = mqtt.Client()
client.username_pw_set(os.getenv('MQTT_USER'), os.getenv('MQTT_PASS'))
client.connect('mosquitto', 1883, 60)
print('MQTT connection OK')
"
```

### Test Gemini API
```bash
docker compose exec storyteller python -c "
from google import genai
import os
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
response = client.models.generate_content(model='gemini-3-flash-preview', contents='Say hello')
print(response.text)
"
```

### Check Email Credentials
```bash
docker compose exec storyteller python -c "
import os
print('SMTP_USER:', os.getenv('SMTP_USER'))
print('SMTP_PASS:', 'SET' if os.getenv('SMTP_PASS') else 'MISSING')
print('SMTP_TO:', os.getenv('SMTP_TO'))
"
```

---

## 📅 Scheduler

The daily email is sent at **7:00 AM ET** automatically via `scripts/scheduler.py`.

### Check Scheduler Status
```bash
docker compose logs storyteller | grep -i scheduler | tail -10
```

---

## 🚀 Quick Commands Cheat Sheet

```bash
# Test email
docker compose exec storyteller python scripts/publisher.py --test

# Preview templates
docker compose exec storyteller python scripts/email_preview.py

# Check status
cat data/status.json | python3 -m json.tool

# View logs
docker compose logs -f storyteller

# Rebuild
docker compose build storyteller && docker compose down storyteller && docker compose up -d storyteller

# Inject message
echo '{"message": "Your text"}' > data/narrative_injection.json
```
