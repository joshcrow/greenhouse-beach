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
        "You are generating a WEEKLY DIGEST for a greenhouse newsletter.",
        "This is a summary of the past week, not a daily update.",
        "",
        "RULES:",
        "- Summarize the week's conditions in 2-3 short paragraphs.",
        "- Highlight any notable events or trends:",
        "  * Temperature extremes (coldest/hottest days)",
        "  * Any concerning patterns (consistently high humidity, etc.)",
        "  * Overall health of the growing environment",
        "- Use <b>bold</b> for key insights.",
        "- Be encouraging and forward-looking.",
        "- Do not use emojis.",
        "",
        "WEEKLY DATA:",
        str(summary),
        "",
        "OUTPUT FORMAT:",
        "",
        "SUBJECT: <Weekly summary subject, e.g., 'This Week: Stable Temps, High Humidity'>",
        "",
        "HEADLINE: <Summary headline, 8-12 words>",
        "",
        "BODY: <2-3 paragraphs summarizing the week and looking ahead>",
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


def build_weekly_email(summary: Dict[str, Any]) -> EmailMessage:
    """Build the weekly digest email."""
    import html
    
    subject, headline, body_text = generate_weekly_narrative(summary)
    
    smtp_from = os.getenv("SMTP_FROM", "Greenhouse Gazette")
    smtp_to = os.getenv("SMTP_TO", "")
    
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
    body_escaped = body_escaped.replace('\n\n', '<br><br>')
    
    # Format stats for display
    def fmt(val):
        return str(round(val)) if val is not None else "N/A"
    
    temp_range = f"{fmt(summary.get('temp_min'))}° – {fmt(summary.get('temp_max'))}°" if summary.get('temp_min') else "N/A"
    humidity_range = f"{fmt(summary.get('humidity_min'))}% – {fmt(summary.get('humidity_max'))}%" if summary.get('humidity_min') else "N/A"
    
    date_range = f"{summary.get('week_start', 'N/A')} to {summary.get('week_end', 'N/A')}"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9f9f9;">
        <div style="background: white; border-radius: 12px; padding: 24px; border: 2px solid #588157;">
            <h1 style="color: #588157; font-size: 24px; margin: 0 0 8px 0;">{headline}</h1>
            <p style="color: #666; font-size: 14px; margin: 0 0 24px 0;">Week of {date_range}</p>
            
            <div style="font-size: 16px; line-height: 1.6; color: #333; margin-bottom: 24px;">
                {body_escaped}
            </div>
            
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <tr style="background: #588157; color: white;">
                    <th style="padding: 12px; text-align: left;">Metric</th>
                    <th style="padding: 12px; text-align: left;">Weekly Range</th>
                    <th style="padding: 12px; text-align: left;">Average</th>
                </tr>
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 12px;">Temperature</td>
                    <td style="padding: 12px;">{temp_range}</td>
                    <td style="padding: 12px;">{fmt(summary.get('temp_avg'))}°</td>
                </tr>
                <tr>
                    <td style="padding: 12px;">Humidity</td>
                    <td style="padding: 12px;">{humidity_range}</td>
                    <td style="padding: 12px;">{fmt(summary.get('humidity_avg'))}%</td>
                </tr>
            </table>
            
            <p style="color: #888; font-size: 12px; margin-top: 24px; text-align: center;">
                Based on {summary.get('days_recorded', 0)} days of data
            </p>
        </div>
    </body>
    </html>
    """
    
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_weekly_digest() -> bool:
    """Generate and send the weekly digest email."""
    weekly = load_weekly_stats()
    
    if not weekly.get("days"):
        log("No weekly data available, skipping digest")
        return False
    
    summary = compute_weekly_summary(weekly)
    log(f"Weekly summary: {summary}")
    
    msg = build_weekly_email(summary)
    
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
