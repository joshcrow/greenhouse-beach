#!/usr/bin/env python3
"""Weekly Digest Generator for the Greenhouse Gazette.

Generates a weekly summary email with trends, notable events,
and a narrative overview of the past week.
"""

import json
import os
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any, Dict, List, Optional, Tuple
import smtplib
import ssl

import narrator
import weather_service


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [weekly] {message}", flush=True)


STATS_PATH = os.getenv("STATS_PATH", "/app/data/stats_24h.json")
STATUS_PATH = os.getenv("STATUS_PATH", "/app/data/status.json")
WEEKLY_STATS_PATH = os.getenv("WEEKLY_STATS_PATH", "/app/data/stats_weekly.json")


def load_weekly_stats() -> Dict[str, Any]:
    """Load or initialize weekly stats file."""
    if os.path.exists(WEEKLY_STATS_PATH):
        try:
            with open(WEEKLY_STATS_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            log(f"Error loading weekly stats: {e}")
    return {"days": [], "week_start": None}


def save_weekly_stats(stats: Dict[str, Any]) -> None:
    """Save weekly stats to file."""
    try:
        with open(WEEKLY_STATS_PATH, "w") as f:
            json.dump(stats, f, indent=2, default=str)
    except Exception as e:
        log(f"Error saving weekly stats: {e}")


def record_daily_snapshot() -> None:
    """Record today's stats to the weekly accumulator.
    
    Call this daily (e.g., at end of day or during daily email).
    """
    weekly = load_weekly_stats()
    
    # Load current 24h stats
    if not os.path.exists(STATS_PATH):
        log("No 24h stats found, skipping daily snapshot")
        return
    
    try:
        with open(STATS_PATH, "r") as f:
            daily_stats = json.load(f)
    except Exception as e:
        log(f"Error loading 24h stats: {e}")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Add today's snapshot
    snapshot = {
        "date": today,
        "stats": daily_stats,
        "recorded_at": datetime.utcnow().isoformat()
    }
    
    # Keep only last 7 days
    weekly["days"] = [d for d in weekly.get("days", []) if d["date"] != today]
    weekly["days"].append(snapshot)
    weekly["days"] = weekly["days"][-7:]  # Keep last 7 days
    
    if not weekly.get("week_start"):
        weekly["week_start"] = today
    
    save_weekly_stats(weekly)
    log(f"Recorded daily snapshot for {today}")


def compute_weekly_summary(weekly: Dict[str, Any]) -> Dict[str, Any]:
    """Compute weekly aggregates from daily snapshots."""
    days = weekly.get("days", [])
    if not days:
        return {}
    
    summary = {
        "days_recorded": len(days),
        "week_start": days[0]["date"] if days else None,
        "week_end": days[-1]["date"] if days else None,
    }
    
    # Aggregate temperature stats
    all_temps = []
    all_humidities = []
    
    for day in days:
        stats = day.get("stats", {})
        # Collect all temperature values
        for key, val in stats.items():
            if "temp" in key.lower() and isinstance(val, (int, float)):
                all_temps.append(val)
            if "humidity" in key.lower() and isinstance(val, (int, float)):
                all_humidities.append(val)
    
    if all_temps:
        summary["temp_min"] = round(min(all_temps))
        summary["temp_max"] = round(max(all_temps))
        summary["temp_avg"] = round(sum(all_temps) / len(all_temps))
    
    if all_humidities:
        summary["humidity_min"] = round(min(all_humidities))
        summary["humidity_max"] = round(max(all_humidities))
        summary["humidity_avg"] = round(sum(all_humidities) / len(all_humidities))
    
    return summary


def build_weekly_prompt(summary: Dict[str, Any]) -> str:
    """Build AI prompt for weekly narrative."""
    lines = [
        "Generate a WEEKLY DIGEST for a greenhouse newsletter.",
        "",
        "RULES:",
        "- Be concise. ONE short paragraph only (3-4 sentences max).",
        "- Mention the temperature range and any notable patterns.",
        "- Use <b>bold</b> for ONE key insight only.",
        "- End with a forward-looking statement for next week.",
        "- No emojis. No number lists.",
        "",
        "DATA:",
        str(summary),
        "",
        "OUTPUT (follow exactly):",
        "",
        "SUBJECT: <Plain text, 5-7 words, e.g., 'Stable Week with Mild Temps'>",
        "",
        "HEADLINE: <8-10 words>",
        "",
        "BODY: <ONE paragraph, 3-4 sentences>",
    ]
    return "\n".join(lines)


def generate_weekly_narrative(summary: Dict[str, Any]) -> Tuple[str, str, str]:
    """Generate weekly narrative using Gemini."""
    prompt = build_weekly_prompt(summary)
    
    try:
        model = narrator.init_model()
        response = model.generate_content(prompt)
        raw_text = narrator._extract_text(response)
        
        if raw_text:
            # Parse response
            subject = "Greenhouse Weekly Digest"
            headline = "Your Week in Review"
            body = raw_text
            
            clean_text = raw_text.replace("**SUBJECT:**", "SUBJECT:").replace("**HEADLINE:**", "HEADLINE:").replace("**BODY:**", "BODY:")
            
            if "SUBJECT:" in clean_text and "HEADLINE:" in clean_text:
                part1, remainder = clean_text.split("HEADLINE:", 1)
                subject = part1.replace("SUBJECT:", "").strip()
                
                if "BODY:" in remainder:
                    part2, body = remainder.split("BODY:", 1)
                    headline = part2.strip()
                    body = body.strip()
                else:
                    lines = remainder.strip().split('\n', 1)
                    headline = lines[0].strip()
                    body = lines[1].strip() if len(lines) > 1 else ""
            
            return subject, headline, body
    except Exception as e:
        log(f"Error generating weekly narrative: {e}")
    
    return "Greenhouse Weekly Digest", "Your Week in Review", "Weekly summary unavailable."


def find_latest_image() -> Optional[str]:
    """Find the latest image from the archive."""
    import glob
    archive_root = "/app/data/archive"
    pattern = os.path.join(archive_root, "**", "*.jpg")
    images = glob.glob(pattern, recursive=True)
    if not images:
        return None
    return max(images, key=os.path.getmtime)


def build_weekly_email(summary: Dict[str, Any]) -> Tuple[EmailMessage, Optional[str]]:
    """Build the weekly digest email with hero image."""
    import html
    import re
    from email.utils import make_msgid
    
    subject, headline, body_text = generate_weekly_narrative(summary)
    
    # Clean subject line
    subject = re.sub(r'<[^>]+>', '', subject)
    subject = re.sub(r'\*+', '', subject)
    subject = subject.strip()
    
    smtp_from = os.getenv("SMTP_FROM", "Greenhouse Gazette")
    smtp_to = os.getenv("SMTP_TO", "")
    
    # Find hero image
    image_path = find_latest_image()
    image_cid = None
    image_bytes = None
    
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            image_cid = make_msgid(domain="greenhouse")[1:-1]
            log(f"Weekly digest will include hero image: {image_path}")
        except Exception as e:
            log(f"Error loading image: {e}")
    
    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = smtp_to
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = f"📊 {subject}"
    
    # Plain text
    msg.set_content(body_text)
    
    # Escape body but allow safe tags
    body_escaped = html.escape(body_text)
    body_escaped = body_escaped.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    body_escaped = body_escaped.replace('\n\n', '<br>')
    
    # Format stats for display
    def fmt(val):
        return str(round(val)) if val is not None else "N/A"
    
    temp_range = f"{fmt(summary.get('temp_min'))}° – {fmt(summary.get('temp_max'))}°" if summary.get('temp_min') else "N/A"
    humidity_range = f"{fmt(summary.get('humidity_min'))}% – {fmt(summary.get('humidity_max'))}%" if summary.get('humidity_min') else "N/A"
    
    week_start = summary.get('week_start', '')
    week_end = summary.get('week_end', '')
    
    # Format dates nicely
    try:
        from datetime import datetime as dt
        start_dt = dt.strptime(week_start, "%Y-%m-%d")
        end_dt = dt.strptime(week_end, "%Y-%m-%d")
        date_range = f"{start_dt.strftime('%b %d')} – {end_dt.strftime('%b %d, %Y')}"
    except (ValueError, TypeError):
        date_range = f"{week_start} to {week_end}"
    
    # Hero image HTML (same as daily)
    hero_html = ""
    if image_cid:
        hero_html = f'''
                    <!-- HERO IMAGE -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border-radius: 12px; overflow: hidden;">
                        <tr>
                            <td>
                                <img src="cid:{image_cid}" alt="Greenhouse this week" style="display:block; width:100%; height:auto; border-radius: 12px;">
                            </td>
                        </tr>
                    </table>
                    
                    <!-- SPACER -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px;">&nbsp;</div>
        '''
    
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <style>
        body {{ margin: 0; padding: 0; background-color: #ffffff; font-family: Arial, sans-serif; }}
        @media (prefers-color-scheme: dark) {{
            body {{ background-color: #171717 !important; color: #f5f5f5 !important; }}
            .dark-bg {{ background-color: #171717 !important; }}
            .dark-text {{ color: #f5f5f5 !important; }}
            .dark-text-muted {{ color: #a3a3a3 !important; }}
            .dark-accent {{ color: #588157 !important; }}
            .dark-border {{ border-color: #588157 !important; }}
        }}
    </style>
</head>
<body style="margin:0; padding:0; background-color:#ffffff; font-family: Arial, sans-serif;">
    <center style="width:100%; background-color:#ffffff;" class="dark-bg">
        <table role="presentation" align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px; margin:0 auto;">
            <tr>
                <td style="padding: 20px;">
                    
                    <!-- HEADER -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                        <tr>
                            <td class="dark-accent" style="padding-bottom: 4px; font-size:24px; font-weight: bold; color:#588157;">
                                {headline}
                            </td>
                        </tr>
                        <tr>
                            <td class="dark-text-muted" style="padding-bottom: 24px; font-size:13px; color:#6b7280;">
                                Week of {date_range}
                            </td>
                        </tr>
                    </table>

                    <!-- NARRATIVE -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-radius: 12px; overflow: hidden;">
                        <tr>
                            <td style="padding: 0;">
                                <p class="dark-text" style="margin:0; line-height:1.6; color:#1e1e1e; font-size: 16px;">
                                    {body_escaped}
                                </p>
                            </td>
                        </tr>
                    </table>

                    <!-- SPACER -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px;">&nbsp;</div>

                    {hero_html}

                    <!-- DATA CARD: Weekly Summary -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 2px solid #588157; border-radius: 12px; overflow: hidden;" class="dark-border dark-bg">
                        <tr>
                            <td style="padding: 16px;">
                                <div class="dark-accent" style="font-size:13px; color:#588157; margin-bottom:12px; font-weight:600; text-transform: uppercase; letter-spacing: 0.5px;">
                                    Weekly Summary
                                </div>
                                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size:14px; border-collapse: collapse;">
                                    <tr>
                                        <th class="dark-text-muted" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal;">Metric</th>
                                        <th class="dark-text-muted" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal;">Range</th>
                                        <th class="dark-text-muted" style="text-align:left; padding:12px 0; border-bottom:1px solid #588157; color:#4b5563; font-weight: normal;">Average</th>
                                    </tr>
                                    <tr>
                                        <td class="dark-text" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">Temperature</td>
                                        <td class="dark-text" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{temp_range}</td>
                                        <td class="dark-text" style="padding:12px 0; border-bottom:1px solid #588157; color:#1e1e1e;">{fmt(summary.get('temp_avg'))}°</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text" style="padding:12px 0; color:#1e1e1e;">Humidity</td>
                                        <td class="dark-text" style="padding:12px 0; color:#1e1e1e;">{humidity_range}</td>
                                        <td class="dark-text" style="padding:12px 0; color:#1e1e1e;">{fmt(summary.get('humidity_avg'))}%</td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                    
                    <!-- FOOTER -->
                    <p class="dark-text-muted" style="color: #9ca3af; font-size: 12px; margin-top: 20px; text-align: center;">
                        Based on {summary.get('days_recorded', 0)} days of data
                    </p>
                    
                </td>
            </tr>
        </table>
    </center>
</body>
</html>
"""
    
    msg.add_alternative(html_body, subtype="html")
    
    # Attach hero image if available
    if image_bytes and image_cid:
        html_part = msg.get_payload()[1]
        html_part.add_related(image_bytes, maintype="image", subtype="jpeg", 
                              cid=f"<{image_cid}>", filename="greenhouse_weekly.jpg")
    
    return msg, image_path


def send_weekly_digest() -> bool:
    """Generate and send the weekly digest email."""
    weekly = load_weekly_stats()
    
    if not weekly.get("days"):
        log("No weekly data available, skipping digest")
        return False
    
    summary = compute_weekly_summary(weekly)
    log(f"Weekly summary: {summary}")
    
    msg, image_path = build_weekly_email(summary)
    
    # Send email
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    
    if not smtp_user or not smtp_password:
        log("SMTP credentials not configured")
        return False
    
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        log("Weekly digest sent successfully!")
        
        # Clear weekly stats after sending
        save_weekly_stats({"days": [], "week_start": None})
        return True
    except Exception as e:
        log(f"Error sending weekly digest: {e}")
        return False


def run_once() -> bool:
    """Entry point for scheduler."""
    return send_weekly_digest()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Record daily snapshot")
    parser.add_argument("--send", action="store_true", help="Send weekly digest now")
    parser.add_argument("--status", action="store_true", help="Show weekly stats status")
    args = parser.parse_args()
    
    if args.record:
        record_daily_snapshot()
    elif args.send:
        send_weekly_digest()
    elif args.status:
        weekly = load_weekly_stats()
        print(f"Days recorded: {len(weekly.get('days', []))}")
        for day in weekly.get("days", []):
            print(f"  - {day['date']}")
    else:
        print("Usage: weekly_digest.py [--record | --send | --status]")
