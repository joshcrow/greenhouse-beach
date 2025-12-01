import glob
import os
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Optional, Tuple

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


def build_email(sensor_data: dict) -> Tuple[EmailMessage, Optional[str]]:
    """Construct the email message and return it along with the image CID (if any)."""

    # Narrative content
    body_text = narrator.generate_update(sensor_data)

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
    today_str = datetime.now().strftime("%Y-%m-%d")
    msg["Subject"] = f"Greenhouse Gazette - {today_str}"

    # Plain-text fallback
    msg.set_content(body_text)

    # HTML body with optional inline image
    if image_cid:
        html_body = f"""
        <html>
          <body>
            <h1>Greenhouse Gazette</h1>
            <p>{body_text}</p>
            <hr />
            <h2>Today's Hero Image</h2>
            <img src="cid:{image_cid}" alt="Greenhouse hero image" style="max-width: 100%; height: auto;" />
          </body>
        </html>
        """
    else:
        html_body = f"""
        <html>
          <body>
            <h1>Greenhouse Gazette</h1>
            <p>{body_text}</p>
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

