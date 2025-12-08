import glob
import html
import os
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, Optional, Tuple

import narrator
import smtplib


ARCHIVE_ROOT = "/app/data/archive"


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [publisher] {message}", flush=True)


def find_latest_image() -> Optional[str]:
    """Return the path to the most recent JPG image in the archive, or None.

    Searches recursively under /app/data/archive for files ending in .jpg/.jpeg.
    """

    pattern_jpg = os.path.join(ARCHIVE_ROOT, "**", "*.jpg")
    pattern_jpeg = os.path.join(ARCHIVE_ROOT, "**", "*.jpeg")
    candidates = glob.glob(pattern_jpg, recursive=True) + glob.glob(pattern_jpeg, recursive=True)

    if not candidates:
        log("No archived JPG images found; proceeding without hero image.")
        return None

    latest = max(candidates, key=os.path.getmtime)
    log(f"Selected latest hero image: {latest}")
    return latest


def load_image_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def build_email(sensor_data: Dict[str, Any]) -> Tuple[EmailMessage, Optional[str]]:
    """Construct the email message and return it along with the image path (if any)."""

    # Narrative content and augmented data (includes weather)
    try:
        subject, headline, body_text, augmented_data = narrator.generate_update(sensor_data)
        # Use augmented data for email template (includes weather info)
        sensor_data = augmented_data
    except Exception as exc:  # noqa: BLE001
        log(f"Narrator failed: {exc}")
        subject = "Greenhouse News"
        headline = "Greenhouse Update"
        body_text = "Error generating update."

    # Hero image
    image_path = find_latest_image()
    image_bytes: Optional[bytes] = None
    image_cid: Optional[str] = None

    if image_path:
        try:
            image_bytes = load_image_bytes(image_path)
            image_cid = make_msgid(domain="greenhouse")[1:-1]  # strip <>
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to load image '{image_path}': {exc}")
            image_bytes = None
            image_cid = None

    # Envelope fields from environment
    smtp_from = os.getenv("SMTP_FROM", "greenhouse@example.com")
    smtp_to = os.getenv("SMTP_TO", "you@example.com")

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = smtp_to
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    # Plain-text fallback
    msg.set_content(body_text)

    # Extract vitals with graceful fallbacks
    indoor_temp = sensor_data.get("temp")
    indoor_humidity = sensor_data.get("humidity")
    outdoor_temp = sensor_data.get("outdoor_temp") or sensor_data.get("outside_temp")
    outdoor_humidity = sensor_data.get("humidity_out") or sensor_data.get("outside_humidity")
    outdoor_condition = sensor_data.get("condition")

    # Extended weather details from weather_service (if available)
    high_temp = sensor_data.get("high_temp")
    low_temp = sensor_data.get("low_temp")
    
    # Use Daily Wind forecast if available (more representative), otherwise current
    wind_mph = sensor_data.get("daily_wind_mph")
    if wind_mph is None:
        wind_mph = sensor_data.get("wind_mph")
        wind_direction = sensor_data.get("wind_direction")
        wind_arrow = sensor_data.get("wind_arrow") or ""
    else:
        wind_direction = sensor_data.get("daily_wind_direction")
        wind_arrow = sensor_data.get("daily_wind_arrow") or ""

    moon_phase = sensor_data.get("moon_phase")
    moon_icon = sensor_data.get("moon_icon") or ""

    def fmt(value):
        """Format value for display, returning N/A for None."""
        return "N/A" if value is None else str(value)

    def fmt_moon_phase(phase_value):
        """Format moon phase as descriptive text."""
        if phase_value is None:
            return "N/A"
        phase = float(phase_value)
        if phase < 0.125 or phase >= 0.875:
            return "New Moon"
        if phase < 0.25:
            return "Waxing Crescent"
        if phase < 0.375:
            return "First Quarter"
        if phase < 0.5:
            return "Waxing Gibbous"
        if phase < 0.625:
            return "Full Moon"
        if phase < 0.75:
            return "Waning Gibbous"
        if phase < 0.875:
            return "Last Quarter"
        return "Waning Crescent"

    def fmt_wind():
        """Format wind display, handling calm conditions."""
        if wind_mph is None:
            return "N/A"
        speed = float(wind_mph)
        if speed < 1.0:
            return "Calm"
        direction = wind_direction or "N/A"
        arrow = wind_arrow or ""
        return f"{arrow} {direction} {speed:.1f} mph"
    
    def fmt_temp_range():
        """Format high/low temp range with color styling."""
        if high_temp is None and low_temp is None:
            return "N/A"
        high_str = f'<span style="color:#dc2626;" class="dark-text-high">{high_temp}°</span>' if high_temp is not None else "N/A"
        low_str = f'<span style="color:#2563eb;" class="dark-text-low">{low_temp}°</span>' if low_temp is not None else "N/A"
        return f"{high_str} / {low_str}"

    # Date subheadline
    date_subheadline = datetime.now().strftime("%A, %B %d, %Y")
    
    # Escape HTML in body text to prevent injection
    body_text_escaped = html.escape(body_text)
    
    # Convert paragraph breaks (double newlines) to HTML breaks (single for tighter spacing)
    body_text_escaped = body_text_escaped.replace('\n\n', '<br>')

    # Build hero image section if available
    hero_section = ""
    if image_cid:
        hero_section = f"""
        <!-- CARD 0: HERO -->
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 0; border-radius: 12px; overflow: hidden;" class="dark-bg-card">
            <tr>
                <td style="padding: 0;">
                    <img src="cid:{image_cid}" alt="Greenhouse hero image" style="display:block; width:100%; height:auto; border:0;">
                </td>
            </tr>
        </table>
        """

    # HTML body with light/dark mode support
    html_body = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="light dark" />
    <meta name="supported-color-schemes" content="light dark" />
    <title>Update</title>
    <style type="text/css">
        /* RESET STYLES */
        body {{ margin: 0; padding: 0; min-width: 100%; background-color: #ffffff; font-family: Arial, sans-serif; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table {{ border-spacing: 0; border-collapse: collapse; }}
        td, th {{ padding: 0; vertical-align: top; }}
        img {{ border: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; display: block; }}
        
        /* PREVENT BLUE LINKS IN APPLE MAIL */
        a[x-apple-data-detectors] {{ color: inherit !important; text-decoration: none !important; font-size: inherit !important; font-family: inherit !important; font-weight: inherit !important; line-height: inherit !important; }}
        
        /* DARK MODE SUPPORT */
        :root {{
            color-scheme: light dark;
            supported-color-schemes: light dark;
        }}

        /* CLIENT SPECIFIC OVERRIDES */
        @media screen and (max-width: 600px) {{
            .container {{ width: 100% !important; max-width: 100% !important; }}
            .mobile-padding {{ padding-left: 16px !important; padding-right: 16px !important; }}
        }}

        @media (prefers-color-scheme: dark) {{
            /* Main Background: Neutral Dark (#171717) */
            body, .body-bg {{ background-color: #171717 !important; color: #f5f5f5 !important; }}
            
            /* Text Colors: Neutral Grays */
            .dark-text-primary {{ color: #f5f5f5 !important; }}
            .dark-text-secondary {{ color: #d4d4d4 !important; }}
            .dark-text-muted {{ color: #a3a3a3 !important; }}
            
            /* Temperature Colors */
            .dark-text-high {{ color: #f87171 !important; }}  /* Lighter red for dark mode */
            .dark-text-low {{ color: #60a5fa !important; }}   /* Lighter blue for dark mode */
            
            /* Accents: Earthier Green (#a3b18a) */
            .dark-text-accent {{ color: #a3b18a !important; }}
            .dark-border {{ border-color: #a3b18a !important; }}
            
            /* Cards: Explicitly match body color in dark mode (No visual fill) */
            .dark-bg-card {{ background-color: #171717 !important; }}
            
            /* Gmail Web hack - match color scheme above */
            u + .body .body-bg {{ background-color: #171717 !important; }}
            u + .body .dark-bg-card {{ background-color: #171717 !important; }}
            u + .body .dark-text-primary {{ color: #f5f5f5 !important; }}
            u + .body .dark-text-secondary {{ color: #d4d4d4 !important; }}
            u + .body .dark-text-muted {{ color: #a3a3a3 !important; }}
            u + .body .dark-text-high {{ color: #f87171 !important; }}
            u + .body .dark-text-low {{ color: #60a5fa !important; }}
            u + .body .dark-text-accent {{ color: #a3b18a !important; }}
            u + .body .dark-border {{ border-color: #a3b18a !important; }}
        }}
    </style>
    <!--[if mso]>
    <style type="text/css">
        body, table, td, th, p, div {{ font-family: Arial, sans-serif !important; }}
        /* Fix for Outlook vertical rhythm */
        td {{ mso-line-height-rule: exactly; }}
    </style>
    <![endif]-->
</head>
<body class="body-bg" style="margin:0; padding:0; background-color:#ffffff; color:#1e1e1e;">
    
    <!-- WRAPPER -->
    <center role="article" aria-roledescription="email" lang="en" style="width:100%; background-color:#ffffff;" class="body-bg">
        
        <!--[if mso]>
        <table role="presentation" align="center" border="0" cellpadding="0" cellspacing="0" width="600">
        <tr>
        <td>
        <![endif]-->
        
        <table role="presentation" class="container" align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px; margin:0 auto;">
            <tr>
                <td style="padding: 20px;" class="mobile-padding">
                    
                    <!-- HEADER -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                        <tr>
                            <td class="dark-text-accent" style="padding-bottom: 4px; font-size:24px; font-weight: bold; color:#588157; line-height: 1.1; mso-line-height-rule: exactly;">
                                {headline}
                            </td>
                        </tr>
                        <tr>
                            <td class="dark-text-muted" style="padding-bottom: 24px; font-size:13px; color:#6b7280; mso-line-height-rule: exactly;">
                                {date_subheadline}
                            </td>
                        </tr>
                    </table>

                    <!-- CARD 1: BODY -->
                    <!-- border-spacing: 0 is critical when using separate borders -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 0; border-radius: 12px; overflow: hidden;" class="dark-bg-card">
                        <tr>
                            <td style="padding: 0;">
                                <p class="dark-text-primary" style="margin:0; line-height:1.6; color:#1e1e1e; font-size: 16px;">
                                    {body_text_escaped}
                                </p>
                            </td>
                        </tr>
                    </table>

                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    {hero_section}

                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    <!-- CARD 2: SENSORS -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 2px solid #588157; border-radius: 12px; overflow: hidden;" class="dark-border dark-bg-card">
                        <tr>
                            <td style="padding: 16px;">
                                <div class="dark-text-accent" style="font-size:13px; color:#588157; margin-bottom:12px; font-weight:600; text-transform: uppercase; letter-spacing: 0.5px;">
                                    Sensors
                                </div>
                                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size:14px; border-collapse: collapse;">
                                    <tr>
                                        <!-- Note: TH tags in Apple Mail are bold by default. Explicitly setting font-weight: normal -->
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #d1d5db; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Location</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #d1d5db; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Temp (°F)</th>
                                        <th class="dark-text-secondary dark-border-table" style="text-align:left; padding:12px 0; border-bottom:1px solid #d1d5db; color:#4b5563; font-weight: normal; mso-line-height-rule: exactly;">Humidity (%)</th>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #d1d5db; color:#1e1e1e;">Indoor</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #d1d5db; color:#1e1e1e;">{fmt(indoor_temp)}</td>
                                        <td class="dark-text-primary dark-border-table" style="padding:12px 0; border-bottom:1px solid #d1d5db; color:#1e1e1e;">{fmt(indoor_humidity)}</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-primary" style="padding:12px 0; color:#1e1e1e;">Outdoor</td>
                                        <td class="dark-text-primary" style="padding:12px 0; color:#1e1e1e;">{fmt(outdoor_temp)}</td>
                                        <td class="dark-text-primary" style="padding:12px 0; color:#1e1e1e;">{fmt(outdoor_humidity)}</td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>

                    <!-- SPACER: 24px -->
                    <div style="height: 24px; line-height: 24px; font-size: 24px; mso-line-height-rule: exactly;">&nbsp;</div>

                    <!-- CARD 3: WEATHER -->
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: separate; border-spacing: 0; border: 2px solid #588157; border-radius: 12px; overflow: hidden;" class="dark-border dark-bg-card">
                        <tr>
                            <td style="padding: 16px;">
                                <div class="dark-text-accent" style="font-size:13px; color:#588157; margin-bottom:12px; font-weight:600; text-transform: uppercase; letter-spacing: 0.5px;">
                                    Today's Weather
                                </div>
                                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="font-size:14px; border-collapse: collapse;">
                                    <tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; width: 40%; vertical-align:middle; mso-line-height-rule: exactly;">Condition</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{fmt(outdoor_condition)}</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">High / Low</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{fmt_temp_range()}</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-secondary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Wind</td>
                                        <td class="dark-text-primary dark-border" style="padding: 12px 0; border-bottom:1px solid #588157; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">{fmt_wind()}</td>
                                    </tr>
                                    <tr>
                                        <td class="dark-text-secondary" style="padding: 12px 0; color:#4b5563; vertical-align:middle; mso-line-height-rule: exactly;">Moon Phase</td>
                                        <td class="dark-text-primary" style="padding: 12px 0; color:#1e1e1e; text-align: right; vertical-align:middle; mso-line-height-rule: exactly;">
                                            <table align="right" border="0" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
                                                <tr>
                                                    <td class="dark-text-primary" style="padding-right: 6px; color:#1e1e1e; vertical-align:middle; font-size: 14px; line-height: 1;">{moon_icon}</td>
                                                    <td class="dark-text-primary" style="color:#1e1e1e; vertical-align:middle; font-size: 14px;">{fmt_moon_phase(moon_phase)}</td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>

                </td>
            </tr>
        </table>
        
        <!--[if mso]>
        </td>
        </tr>
        </table>
        <![endif]-->
        
    </center>
</body>
</html>
"""

    msg.add_alternative(html_body, subtype="html")

    # Attach image as inline related part if available
    if image_bytes and image_cid:
        try:
            # The HTML part is the last part after set_content + add_alternative
            html_part = msg.get_payload()[-1]
            html_part.add_related(
                image_bytes,
                maintype="image",
                subtype="jpeg",
                cid=f"<{image_cid}>",
                filename=os.path.basename(image_path),
            )
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to attach inline image: {exc}")

    return msg, image_path


def send_email(msg: EmailMessage) -> None:
    """Send the email via SMTP over SSL using environment variables."""

    smtp_server = os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not smtp_server:
        log("ERROR: SMTP_SERVER/SMTP_HOST is not configured; cannot send email.")
        return

    log(f"Connecting to SMTP server {smtp_server}:{smtp_port} using SSL...")

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        log("Email sent successfully.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error while sending email: {exc}")


def run_once() -> None:
    """Run a one-off generation and delivery with dummy sensor data."""

    sensor_data = {"temp": 75, "humidity": 50}
    log(f"Preparing email with sensor data: {sensor_data}")
    msg, image_path = build_email(sensor_data)
    if image_path:
        log(f"Email will include hero image: {image_path}")
    else:
        log("Email will be text-only (no hero image found).")

    send_email(msg)


if __name__ == "__main__":
    run_once()

