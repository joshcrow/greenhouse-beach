"""Broadcast & Injection Email Polling Service.

Polls a dedicated Gmail inbox for broadcast and narrative injection commands.

Email subject formats:
  BROADCAST: Your Title Here  -> Creates broadcast card in email
  INJECT: Your message here   -> Injects into narrative (birthdays, events)
  INJECT HIGH: Your message   -> High priority injection (opens narrative)

Creates:
  /app/data/broadcast.json - publisher.py consumes for broadcast card
  /app/data/narrative_injection.json - narrator.py consumes for narrative
"""

import email
import imaplib
import json
import os
from datetime import datetime
from email.header import decode_header

from utils.logger import create_logger

log = create_logger("broadcast_email")

# Lazy settings loader for app.config integration
_settings = None

def _get_settings():
    """Get settings lazily to avoid import-time failures."""
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception:
            _settings = None
    return _settings


def decode_email_subject(subject) -> str:
    """Decode email subject which may be encoded."""
    if subject is None:
        return ""
    decoded_parts = decode_header(subject)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def get_email_body(msg) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def check_for_broadcast() -> bool:
    """Check Gmail inbox for broadcast commands.
    
    Returns True if a broadcast was found and queued.
    
    Security: Only accepts emails from ALLOWED_SENDERS.
    Format: Subject must start with "BROADCAST:" (case-insensitive).
    """
    # Use same credentials as SMTP sending
    imap_server = "imap.gmail.com"
    email_addr = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    broadcast_path = os.getenv("BROADCAST_PATH", "/app/data/broadcast.json")
    
    # Security: Only accept broadcasts from these senders
    # Configure via BROADCAST_ALLOWED_SENDERS env var (comma-separated)
    allowed_env = os.getenv("BROADCAST_ALLOWED_SENDERS", "")
    ALLOWED_SENDERS = [s.strip() for s in allowed_env.split(",") if s.strip()]
    
    if not ALLOWED_SENDERS:
        log("WARNING: BROADCAST_ALLOWED_SENDERS not configured, rejecting all broadcasts")
        return False
    
    if not email_addr or not password:
        log("ERROR: SMTP_USER or SMTP_PASSWORD not configured")
        return False
    
    try:
        # Connect to Gmail IMAP
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_addr, password)
        mail.select("inbox")
        
        # Search for unread emails with BROADCAST in subject
        _, data = mail.search(None, '(UNSEEN SUBJECT "BROADCAST:")')
        
        email_ids = data[0].split()
        if not email_ids:
            mail.logout()
            return False
        
        # Process only the first matching email
        email_id = email_ids[0]
        _, msg_data = mail.fetch(email_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        # Security: Verify sender is allowed
        from_header = msg.get("From", "")
        sender_email = from_header
        # Extract email from "Name <email@example.com>" format
        if "<" in from_header and ">" in from_header:
            sender_email = from_header.split("<")[1].split(">")[0]
        sender_email = sender_email.lower().strip()
        
        if sender_email not in [s.lower() for s in ALLOWED_SENDERS]:
            log(f"Broadcast rejected: unauthorized sender '{sender_email}'")
            mail.store(email_id, "+FLAGS", "\\Seen")  # Mark read to avoid reprocessing
            mail.logout()
            return False
        
        # Parse subject for title
        subject = decode_email_subject(msg["Subject"])
        title = subject.replace("BROADCAST:", "").strip()
        if not title:
            title = "📢 From the Editor"
        
        # Get message body
        body = get_email_body(msg).strip()
        
        if not body:
            log(f"Broadcast email found but body is empty, skipping")
            # Mark as read anyway to avoid reprocessing
            mail.store(email_id, "+FLAGS", "\\Seen")
            mail.logout()
            return False
        
        # Create broadcast.json
        broadcast_data = {
            "title": title,
            "message": body,
            "queued_at": datetime.utcnow().isoformat() + "Z"
        }
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(broadcast_path), exist_ok=True)
        
        with open(broadcast_path, "w", encoding="utf-8") as f:
            json.dump(broadcast_data, f, indent=2)
        
        log(f"Broadcast queued: '{title}' ({len(body)} chars)")
        
        # Mark email as read (or delete it)
        mail.store(email_id, "+FLAGS", "\\Seen")
        # Optionally delete: mail.store(email_id, "+FLAGS", "\\Deleted")
        
        mail.logout()
        return True
        
    except imaplib.IMAP4.error as exc:
        log(f"IMAP error: {exc}")
        return False
    except Exception as exc:
        log(f"Broadcast email check failed: {exc}")
        return False


def check_for_injection() -> bool:
    """Check Gmail inbox for narrative injection commands.
    
    Returns True if an injection was found and queued.
    
    Security: Only accepts emails from ALLOWED_SENDERS.
    Format: Subject must start with "INJECT:" (case-insensitive).
            Use "INJECT HIGH:" for high priority (opens narrative).
    """
    imap_server = "imap.gmail.com"
    email_addr = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    injection_path = os.getenv("NARRATIVE_INJECTION_PATH", "/app/data/narrative_injection.json")
    
    # Security: Only accept injections from these senders
    allowed_env = os.getenv("BROADCAST_ALLOWED_SENDERS", "")
    ALLOWED_SENDERS = [s.strip() for s in allowed_env.split(",") if s.strip()]
    
    if not ALLOWED_SENDERS:
        log("WARNING: BROADCAST_ALLOWED_SENDERS not configured, rejecting all injections")
        return False
    
    if not email_addr or not password:
        log("ERROR: SMTP_USER or SMTP_PASSWORD not configured")
        return False
    
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_addr, password)
        mail.select("inbox")
        
        # Search for unread emails with INJECT in subject
        _, data = mail.search(None, '(UNSEEN SUBJECT "INJECT:")')
        
        email_ids = data[0].split()
        if not email_ids:
            mail.logout()
            return False
        
        # Process only the first matching email
        email_id = email_ids[0]
        _, msg_data = mail.fetch(email_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        # Security: Verify sender is allowed
        from_header = msg.get("From", "")
        sender_email = from_header
        if "<" in from_header and ">" in from_header:
            sender_email = from_header.split("<")[1].split(">")[0]
        sender_email = sender_email.lower().strip()
        
        if sender_email not in [s.lower() for s in ALLOWED_SENDERS]:
            log(f"Injection rejected: unauthorized sender '{sender_email}'")
            mail.store(email_id, "+FLAGS", "\\Seen")
            mail.logout()
            return False
        
        # Parse subject for message and priority
        subject = decode_email_subject(msg["Subject"])
        subject_upper = subject.upper()
        
        # Check for high priority
        priority = None
        if subject_upper.startswith("INJECT HIGH:"):
            priority = "high"
            message = subject.replace("INJECT HIGH:", "", 1).replace("INJECT high:", "", 1).strip()
        elif subject_upper.startswith("INJECT:"):
            message = subject.replace("INJECT:", "", 1).replace("inject:", "", 1).strip()
        else:
            message = subject.strip()
        
        # If subject message is short, use body instead
        body = get_email_body(msg).strip()
        if len(message) < 10 and body:
            message = body
        
        if not message:
            log("Injection email found but message is empty, skipping")
            mail.store(email_id, "+FLAGS", "\\Seen")
            mail.logout()
            return False
        
        # Create narrative_injection.json
        injection_data = {
            "message": message,
            "queued_at": datetime.utcnow().isoformat() + "Z"
        }
        if priority:
            injection_data["priority"] = priority
        
        os.makedirs(os.path.dirname(injection_path), exist_ok=True)
        
        with open(injection_path, "w", encoding="utf-8") as f:
            json.dump(injection_data, f, indent=2)
        
        priority_str = " (HIGH PRIORITY)" if priority else ""
        log(f"Injection queued{priority_str}: '{message[:50]}...' ({len(message)} chars)")
        
        mail.store(email_id, "+FLAGS", "\\Seen")
        mail.logout()
        return True
        
    except imaplib.IMAP4.error as exc:
        log(f"IMAP error: {exc}")
        return False
    except Exception as exc:
        log(f"Injection email check failed: {exc}")
        return False


def poll_broadcast_inbox() -> None:
    """Wrapper for scheduler integration with error handling.
    
    Checks for both broadcast and injection emails.
    """
    try:
        broadcast_found = check_for_broadcast()
        if broadcast_found:
            log("Broadcast message queued for next Gazette")
    except Exception as exc:
        log(f"Error polling broadcast inbox: {exc}")
    
    try:
        injection_found = check_for_injection()
        if injection_found:
            log("Narrative injection queued for next Gazette")
    except Exception as exc:
        log(f"Error polling injection inbox: {exc}")


if __name__ == "__main__":
    # Manual test
    check_for_broadcast()
    check_for_injection()
