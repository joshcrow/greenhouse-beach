"""Email sending utilities for Greenhouse Gazette.

Extracted from publisher.py to separate concerns and improve testability.

Usage:
    from email_sender import send_email
    send_email(msg, recipients=["user@example.com"])
"""

import ssl
import smtplib
from email.message import EmailMessage
from typing import List, Optional

from utils.logger import create_logger

log = create_logger("email_sender")

# Lazy import of settings to avoid circular imports
_settings = None

def _get_settings():
    """Get settings lazily to avoid import-time failures."""
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception as e:
            log(f"Failed to load app.config.settings: {e}")
            _settings = None
    return _settings


def send_email(
    msg: EmailMessage,
    recipients: Optional[List[str]] = None,
) -> bool:
    """Send an email via SMTP over SSL.
    
    Args:
        msg: The EmailMessage to send
        recipients: List of recipient addresses (overrides msg["To"] if provided)
    
    Returns:
        True if email sent successfully, False otherwise
    
    Configuration loaded from app.config.settings (falls back to env vars).
    """
    settings = _get_settings()
    
    if settings:
        smtp_server = settings.smtp_server_host
        smtp_port = settings.smtp_port
        smtp_user = settings.smtp_user
        smtp_pass = settings.smtp_password
    else:
        # Fallback to environment variables if settings not available
        import os
        smtp_server = os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "465"))
        smtp_user = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")

    if not smtp_server:
        log("ERROR: SMTP_SERVER/SMTP_HOST is not configured; cannot send email.")
        return False

    log(f"Connecting to SMTP server {smtp_server}:{smtp_port} using SSL...")

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg, to_addrs=recipients)
        
        recipient_count = len(recipients) if recipients else "unknown"
        log(f"Email sent successfully to {recipient_count} recipients.")
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"Error while sending email: {exc}")
        return False


def get_recipients_from_env() -> List[str]:
    """Get recipient list from settings or environment.
    
    Returns:
        List of email addresses, or empty list if not configured
    """
    settings = _get_settings()
    if settings:
        return settings.smtp_recipients
    
    # Fallback to environment variable
    import os
    smtp_to = os.getenv("SMTP_TO", "")
    return [addr.strip() for addr in smtp_to.split(",") if addr.strip()]
