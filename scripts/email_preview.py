#!/usr/bin/env python3
"""Email template preview server with hot reload.

Renders email templates with mock data for design iteration.
Templates reload on every request - no restart needed.

Usage:
    python scripts/email_preview.py
    
Then visit: http://localhost:8081/
"""

import http.server
import json
import os
import socketserver
import sys
from datetime import datetime
from urllib.parse import parse_qs, urlparse

# Add scripts to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import create_logger

log = create_logger("preview")

PREVIEW_PORT = int(os.getenv("PREVIEW_PORT", "8081"))

# Mock data for template preview
MOCK_DATA = {
    "normal": {
        "subject": "Clear skies over the sound",
        "headline": "Greenhouse running smooth, nice day ahead.",
        "body_html": "Temperature's holding steady at 68°. Outside sitting at 52°, humidity reasonable. Wind's light out of the southwest. Sound's calm. Tomorrow looks about the same. Good growing weather.",
        "date_display": datetime.now().strftime("%A, %B %d, %Y"),
        "interior_temp": 68,
        "interior_humidity": 45,
        "interior_stale": False,
        "exterior_temp": 52,
        "exterior_humidity": 72,
        "exterior_stale": False,
        "condition": "Clear",
        "condition_emoji": "☀️",
        "high_temp": 58,
        "low_temp": 42,
        "wind_display": "↗ SW 8 mph",
        "sunrise": "7:12 AM",
        "sunset": "5:04 PM",
        "moon_icon": "🌕",
        "moon_phase": "Full Moon",
        "tide_display": "High 9:30 AM · Low 3:15 PM",
        "image_cid": None,
        "chart_cid": None,
        "stats_24h": {
            "interior_temp_max": 72,
            "interior_temp_min": 62,
            "interior_humidity_max": 48,
            "interior_humidity_min": 40,
            "exterior_temp_max": 55,
            "exterior_temp_min": 38,
            "exterior_humidity_max": 85,
            "exterior_humidity_min": 65,
        },
        "riddle_text": "I have keys but no locks. I have space but no room. You can enter but can't go inside. What am I?",
        "yesterday_answer": None,
        "alerts": None,
        "test_mode": True,
        "debug_info": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "battery": 3.8,
            "model": "gemini-2.5-flash",
        },
    },
    "alerts": {
        "subject": "🧊 Frost Alert - Protect the greenhouse",
        "headline": "Cold snap incoming, temps dropping fast tonight.",
        "body_html": "Temperature's plummeting. Expected low of 28°F. Northeast wind pushing cold air off the sound. <b>Check the heater.</b> Satellite battery getting low. Tomorrow should warm back up.",
        "date_display": datetime.now().strftime("%A, %B %d, %Y"),
        "interior_temp": 58,
        "interior_humidity": 52,
        "interior_stale": False,
        "exterior_temp": 34,
        "exterior_humidity": 88,
        "exterior_stale": False,
        "condition": "Clouds",
        "condition_emoji": "☁️",
        "high_temp": 38,
        "low_temp": 28,
        "wind_display": "↗ NE 18 mph",
        "sunrise": "7:14 AM",
        "sunset": "5:02 PM",
        "moon_icon": "🌖",
        "moon_phase": "Waning Gibbous",
        "tide_display": "High 10:15 AM · Low 4:02 PM",
        "image_cid": None,
        "chart_cid": None,
        "stats_24h": {
            "interior_temp_max": 68,
            "interior_temp_min": 55,
            "interior_humidity_max": 55,
            "interior_humidity_min": 48,
            "exterior_temp_max": 45,
            "exterior_temp_min": 32,
            "exterior_humidity_max": 92,
            "exterior_humidity_min": 78,
        },
        "riddle_text": "I'm clear as day but disappear at night. I form on grass but hate the light. What am I?",
        "yesterday_answer": "A keyboard",
        "alerts": [
            {"icon": "❄️", "title": "Frost Risk", "detail": "Low of 28°F tonight - protect tender plants"},
            {"icon": "🔋", "title": "Battery Low", "detail": "Outdoor sensor at 3.2V - needs charging"},
            {"icon": "💨", "title": "High Wind", "detail": "Gusts up to 25 mph expected"},
        ],
        "test_mode": True,
        "debug_info": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "battery": 3.2,
            "model": "gemini-2.5-flash",
        },
    },
    "stale": {
        "subject": "Sensor issues - data gaps",
        "headline": "Having some sensor troubles, bear with us.",
        "body_html": "Interior sensor went quiet a few hours ago. Outside reading is current. Weather looks fine otherwise. Need to check the hardware.",
        "date_display": datetime.now().strftime("%A, %B %d, %Y"),
        "interior_temp": None,
        "interior_humidity": None,
        "interior_stale": True,
        "exterior_temp": 55,
        "exterior_humidity": 70,
        "exterior_stale": False,
        "condition": "Partly Cloudy",
        "condition_emoji": "⛅",
        "high_temp": 60,
        "low_temp": 45,
        "wind_display": "↗ E 5 mph",
        "sunrise": "7:10 AM",
        "sunset": "5:06 PM",
        "moon_icon": "🌓",
        "moon_phase": "First Quarter",
        "tide_display": "High 11:00 AM · Low 5:30 PM",
        "image_cid": None,
        "chart_cid": None,
        "stats_24h": None,
        "riddle_text": None,
        "yesterday_answer": None,
        "alerts": None,
        "test_mode": True,
        "debug_info": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "battery": 3.6,
            "model": "gemini-2.5-flash",
        },
    },
}


def render_email(scenario: str = "normal") -> str:
    """Render email template with mock data. Reloads template on each call."""
    # Import fresh each time for hot reload
    import importlib
    import email_templates
    importlib.reload(email_templates)
    
    data = MOCK_DATA.get(scenario, MOCK_DATA["normal"])
    return email_templates.render_daily_email(**data)


def render_index() -> str:
    """Render the preview index page."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>Email Template Preview</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, sans-serif; 
            max-width: 900px; 
            margin: 40px auto; 
            padding: 20px;
            background: #f5f5f5;
        }
        h1 { color: #6b9b5a; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .scenarios { display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 30px; }
        .scenario { 
            padding: 15px 25px; 
            background: white; 
            border-radius: 8px; 
            text-decoration: none;
            color: #333;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: all 0.2s;
        }
        .scenario:hover { 
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }
        .scenario h3 { margin: 0 0 5px 0; color: #6b9b5a; }
        .scenario p { margin: 0; font-size: 13px; color: #666; }
        .tip { 
            background: #e8f5e9; 
            padding: 15px; 
            border-radius: 8px; 
            font-size: 14px;
            color: #2e7d32;
        }
        code { background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>🌱 Email Template Preview</h1>
    <p class="subtitle">Hot reload enabled - edit templates and refresh to see changes</p>
    
    <div class="scenarios">
        <a href="/preview?scenario=normal" class="scenario">
            <h3>☀️ Normal Day</h3>
            <p>Clear weather, all systems nominal</p>
        </a>
        <a href="/preview?scenario=alerts" class="scenario">
            <h3>❄️ With Alerts</h3>
            <p>Frost risk, low battery, high wind</p>
        </a>
        <a href="/preview?scenario=stale" class="scenario">
            <h3>⚠️ Stale Data</h3>
            <p>Missing sensor readings</p>
        </a>
    </div>
    
    <div class="tip">
        <strong>💡 Tip:</strong> Edit files in <code>templates/</code> and refresh the preview. 
        No server restart needed!
    </div>
</body>
</html>"""


class PreviewHandler(http.server.BaseHTTPRequestHandler):
    """Handler for email preview requests."""

    def log_message(self, format, *args):
        log(f"{self.address_string()} - {args[0]}")

    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(render_index().encode("utf-8"))
            
        elif parsed.path == "/preview":
            query = parse_qs(parsed.query)
            scenario = query.get("scenario", ["normal"])[0]
            
            try:
                html = render_email(scenario)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Error rendering template: {e}".encode("utf-8"))
                log(f"ERROR: {e}")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")


def main():
    log(f"Starting email preview server on port {PREVIEW_PORT}")
    log(f"Visit: http://localhost:{PREVIEW_PORT}/")
    log("Hot reload enabled - edit templates and refresh!")
    
    with socketserver.TCPServer(("0.0.0.0", PREVIEW_PORT), PreviewHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
