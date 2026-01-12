"""Unified Inbox Monitor - Handles BROADCAST, INJECT, and GUESS commands.

Extends broadcast_email.py functionality to add riddle game support.
Polls Gmail inbox for commands and routes to appropriate handlers.

Email subject formats:
  BROADCAST: Your Title Here  -> Creates broadcast card in email
  INJECT: Your message here   -> Injects into narrative
  INJECT HIGH: Your message   -> High priority injection
  GUESS [YYYY-MM-DD]: answer  -> Riddle game guess
"""

import email
import imaplib
import json
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

from utils.io import atomic_write_json, atomic_read_json
from utils.logger import create_logger

log = create_logger("inbox_monitor")

# Import game modules
import narrator
import scorekeeper

# Lazy settings loader
_settings = None

def _get_settings():
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception:
            _settings = None
    return _settings


# =============================================================================
# CONFIGURATION
# =============================================================================

def _get_path(attr: str, default: str) -> str:
    """Get path from settings or use default."""
    cfg = _get_settings()
    return getattr(cfg, attr, None) or default

_RATE_LIMIT_PATH = "/app/data/reply_rate_limit.json"
_RIDDLE_STATE_PATH_DEFAULT = "/app/data/riddle_state.json"

def _get_riddle_state_path() -> str:
    cfg = _get_settings()
    return cfg.riddle_state_path if cfg else _RIDDLE_STATE_PATH_DEFAULT

MAX_REPLIES_PER_USER_PER_DAY = 5
POLL_INTERVAL_MINUTES = 5  # Kept at 5 minutes for Gmail friendliness

# Auto-reply detection
AUTO_REPLY_HEADERS = [
    "X-Auto-Response-Suppress",
    "Auto-Submitted",
]

AUTO_REPLY_SUBJECTS = [
    "automatic reply",
    "out of office",
    "undeliverable",
    "delivery status",
    "returned mail",
    "auto-reply",
    "autoreply",
]


# =============================================================================
# UTILITY FUNCTIONS (shared with broadcast_email.py)
# =============================================================================

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


def extract_sender_email(msg) -> str:
    """Extract sender email from From header."""
    from_header = msg.get("From", "")
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].lower().strip()
    return from_header.lower().strip()


def parse_email_timestamp(msg) -> Optional[datetime]:
    """Parse the Date header to get email send time."""
    date_header = msg.get("Date")
    if not date_header:
        return None
    try:
        return parsedate_to_datetime(date_header).replace(tzinfo=None)
    except Exception:
        return None


# =============================================================================
# SAFETY FILTERS
# =============================================================================

def is_auto_reply(msg) -> bool:
    """Check if message is an auto-reply (avoid reply loops)."""
    # Check headers
    for header in AUTO_REPLY_HEADERS:
        value = msg.get(header)
        if value:
            # Auto-Submitted: auto-replied, auto-generated, etc.
            if header == "Auto-Submitted" and value.lower() != "no":
                return True
            # X-Auto-Response-Suppress: present means suppress
            if header == "X-Auto-Response-Suppress":
                return True
    
    # Check Precedence header
    precedence = msg.get("Precedence", "").lower()
    if precedence in ("bulk", "auto_reply", "junk"):
        return True
    
    # Check subject keywords
    subject = decode_email_subject(msg.get("Subject", "")).lower()
    return any(phrase in subject for phrase in AUTO_REPLY_SUBJECTS)


def _load_rate_limits() -> Dict[str, List[str]]:
    """Load rate limit tracking data."""
    return atomic_read_json(_RATE_LIMIT_PATH, default={})


def _save_rate_limits(data: Dict[str, List[str]]) -> None:
    """Save rate limit tracking data."""
    atomic_write_json(_RATE_LIMIT_PATH, data)


def can_send_reply(user_email: str) -> bool:
    """Check if user is under rate limit (max 5 replies per 24h)."""
    user_email = user_email.lower().strip()
    limits = _load_rate_limits()
    
    user_timestamps = limits.get(user_email, [])
    if not user_timestamps:
        return True
    
    # Filter to last 24 hours
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    recent = [ts for ts in user_timestamps if ts > cutoff]
    
    return len(recent) < MAX_REPLIES_PER_USER_PER_DAY


def record_reply_sent(user_email: str) -> None:
    """Record that we sent a reply to this user."""
    user_email = user_email.lower().strip()
    limits = _load_rate_limits()
    
    user_timestamps = limits.get(user_email, [])
    user_timestamps.append(datetime.utcnow().isoformat() + "Z")
    
    # Prune old entries (keep last 7 days)
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
    user_timestamps = [ts for ts in user_timestamps if ts > cutoff]
    
    limits[user_email] = user_timestamps
    _save_rate_limits(limits)


# =============================================================================
# REPLY SENDING
# =============================================================================

def send_reply(original_msg, body: str, sender_email: str) -> bool:
    """Send a reply that threads properly with the original email."""
    cfg = _get_settings()
    smtp_user = cfg.smtp_user if cfg else None
    smtp_password = cfg.smtp_password if cfg else None
    smtp_server = cfg.smtp_server_host if cfg else "smtp.gmail.com"
    smtp_port = cfg.smtp_port if cfg else 587
    
    if not smtp_user or not smtp_password:
        log("ERROR: SMTP credentials not configured")
        return False
    
    if not can_send_reply(sender_email):
        log(f"Rate limit exceeded for {sender_email}, skipping reply")
        return False
    
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "Re: " + decode_email_subject(original_msg.get("Subject", ""))
        msg["To"] = sender_email
        msg["From"] = smtp_user
        
        # Threading headers
        original_id = original_msg.get("Message-ID")
        if original_id:
            msg["In-Reply-To"] = original_id
            msg["References"] = original_id
        
        # Mark as auto-reply to prevent loops
        msg["Auto-Submitted"] = "auto-replied"
        msg["X-Auto-Response-Suppress"] = "All"
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        record_reply_sent(sender_email)
        log(f"Sent reply to {sender_email}")
        return True
        
    except Exception as exc:
        log(f"Failed to send reply to {sender_email}: {exc}")
        return False


# =============================================================================
# GUESS HANDLING
# =============================================================================

def parse_guess_subject(subject: str) -> Optional[Tuple[str, str]]:
    """
    Parse: GUESS [2026-01-12]: the wind
    Returns: (date_id, guess_text) or None
    """
    match = re.search(
        r"GUESS\s*\[(\d{4}-\d{2}-\d{2})\]\s*:?\s*(.*)",
        subject,
        re.IGNORECASE
    )
    if match:
        return match.group(1), match.group(2).strip()
    return None


def _load_riddle_state() -> Dict[str, Any]:
    """Load current riddle state."""
    return atomic_read_json(_get_riddle_state_path(), default={})


def handle_guess(msg, sender_email: str) -> bool:
    """Process a riddle guess email."""
    subject = decode_email_subject(msg.get("Subject", ""))
    
    parsed = parse_guess_subject(subject)
    if not parsed:
        # Try to get guess from body if subject format is wrong
        body = get_email_body(msg).strip()
        if body and len(body) < 200:
            # Assume the body is the guess, but we need the date
            riddle_state = _load_riddle_state()
            current_date = riddle_state.get("date")
            if current_date:
                parsed = (current_date, body)
            else:
                send_reply(msg, 
                    "Ahoy! Format yer guess like this in the subject:\n"
                    "GUESS [YYYY-MM-DD]: your answer\n\n"
                    "Check today's Gazette for the riddle date.",
                    sender_email)
                return False
        else:
            send_reply(msg,
                "Ahoy! Format yer guess like this in the subject:\n"
                "GUESS [YYYY-MM-DD]: your answer\n\n"
                "Check today's Gazette for the riddle date.",
                sender_email)
            return False
    
    date_id, guess_text = parsed
    
    # If guess is empty, try body
    if not guess_text:
        guess_text = get_email_body(msg).strip()[:200]
    
    if not guess_text:
        send_reply(msg,
            "Ye sent an empty bottle, matey. Put yer guess in it next time.",
            sender_email)
        return False
    
    # Validate date matches current riddle
    riddle_state = _load_riddle_state()
    current_date = riddle_state.get("date")
    
    if not current_date:
        send_reply(msg,
            "The Captain hasn't posed a riddle yet. Check back after the morning Gazette.",
            sender_email)
        return False
    
    if date_id != current_date:
        send_reply(msg,
            f"That riddle is ancient history, matey. Today's riddle is dated {current_date}. "
            "Check the latest Gazette.",
            sender_email)
        return False
    
    # Get email timestamp for fair first-solver determination
    email_timestamp = parse_email_timestamp(msg) or datetime.utcnow()
    
    # Judge the guess
    correct_answer = riddle_state.get("answer", "")
    riddle_text = riddle_state.get("riddle", "")
    
    judgment = narrator.judge_riddle(
        user_guess=guess_text,
        correct_answer=correct_answer,
        riddle_text=riddle_text
    )
    
    # Record the attempt
    result = scorekeeper.record_attempt(
        user_email=sender_email,
        guess_is_correct=judgment["correct"],
        riddle_date=date_id,
        email_timestamp=email_timestamp
    )
    
    # Build reply
    reply_text = judgment["reply_text"]
    
    if result["status"] == "correct":
        if result.get("is_first"):
            reply_text += f" First to crack it today! +{result['points']} points."
        else:
            reply_text += f" +{result['points']} point. You're #{result['rank']} to solve it."
    elif result["status"] == "already_solved":
        reply_text = "Ye already cracked this one, matey. Save yer ink for tomorrow's riddle."
    elif result["status"] == "stale_riddle":
        reply_text = "That riddle's from another tide. Check the latest Gazette."
    # status == "wrong" uses the AI's reply_text as-is
    
    send_reply(msg, reply_text, sender_email)
    return True


# =============================================================================
# BROADCAST & INJECT HANDLERS (from broadcast_email.py)
# =============================================================================

def handle_broadcast(msg, sender_email: str) -> bool:
    """Process a broadcast command email."""
    cfg = _get_settings()
    broadcast_path = os.path.join(cfg.data_dir, "broadcast.json") if cfg else "/app/data/broadcast.json"
    
    subject = decode_email_subject(msg.get("Subject", ""))
    title = subject.upper().replace("BROADCAST:", "").strip()
    if not title:
        title = "📢 From the Editor"
    
    body = get_email_body(msg).strip()
    if not body:
        log(f"Broadcast email from {sender_email} has empty body, skipping")
        return False
    
    broadcast_data = {
        "title": title,
        "message": body,
        "queued_at": datetime.utcnow().isoformat() + "Z"
    }
    
    os.makedirs(os.path.dirname(broadcast_path), exist_ok=True)
    
    with open(broadcast_path, "w", encoding="utf-8") as f:
        json.dump(broadcast_data, f, indent=2)
    
    log(f"Broadcast queued from {sender_email}: '{title}' ({len(body)} chars)")
    return True


def handle_injection(msg, sender_email: str) -> bool:
    """Process a narrative injection command email."""
    cfg = _get_settings()
    injection_path = os.path.join(cfg.data_dir, "narrative_injection.json") if cfg else "/app/data/narrative_injection.json"
    
    subject = decode_email_subject(msg.get("Subject", ""))
    subject_upper = subject.upper()
    
    priority = None
    if "INJECT HIGH:" in subject_upper:
        priority = "high"
        message = re.sub(r"INJECT\s+HIGH\s*:\s*", "", subject, flags=re.IGNORECASE).strip()
    else:
        message = re.sub(r"INJECT\s*:\s*", "", subject, flags=re.IGNORECASE).strip()
    
    # If subject message is short, use body
    body = get_email_body(msg).strip()
    if len(message) < 10 and body:
        message = body
    
    if not message:
        log(f"Injection email from {sender_email} has empty message, skipping")
        return False
    
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
    log(f"Injection queued{priority_str} from {sender_email}: '{message[:50]}...'")
    return True


# =============================================================================
# MAIN INBOX POLLING
# =============================================================================

def poll_inbox() -> None:
    """Poll inbox for all command types: BROADCAST, INJECT, GUESS."""
    cfg = _get_settings()
    
    # Check kill switch
    if cfg and hasattr(cfg, 'riddle_game_enabled') and not cfg.riddle_game_enabled:
        log("Riddle game disabled, skipping GUESS processing")
        game_enabled = False
    else:
        game_enabled = True
    
    imap_server = "imap.gmail.com"
    cfg = _get_settings()
    email_addr = cfg.smtp_user if cfg else None
    password = cfg.smtp_password if cfg else None
    
    # Sender allow-lists
    admin_senders_env = os.getenv("BROADCAST_ALLOWED_SENDERS", "")
    admin_senders = [s.strip().lower() for s in admin_senders_env.split(",") if s.strip()]
    
    player_emails = [e.lower() for e in cfg.smtp_recipients] if cfg else []
    
    if not email_addr or not password:
        log("ERROR: SMTP_USER or SMTP_PASSWORD not configured")
        return
    
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_addr, password)
        mail.select("inbox")
        
        # Search for unread emails
        _, data = mail.search(None, "(UNSEEN)")
        email_ids = data[0].split()
        
        if not email_ids:
            mail.logout()
            return
        
        log(f"Found {len(email_ids)} unread email(s)")
        
        for email_id in email_ids:
            try:
                _, msg_data = mail.fetch(email_id, "(RFC822)")
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                sender = extract_sender_email(msg)
                subject = decode_email_subject(msg.get("Subject", ""))
                subject_upper = subject.upper()
                
                # Skip auto-replies
                if is_auto_reply(msg):
                    log(f"Skipping auto-reply from {sender}")
                    mail.store(email_id, "+FLAGS", "\\Seen")
                    continue
                
                # Route based on sender and subject
                handled = False
                
                # Admin commands
                if sender in admin_senders:
                    if subject_upper.startswith("BROADCAST:"):
                        handled = handle_broadcast(msg, sender)
                    elif "INJECT" in subject_upper and ":" in subject:
                        handled = handle_injection(msg, sender)
                    elif subject_upper.startswith("GUESS") and game_enabled:
                        handled = handle_guess(msg, sender)
                
                # Player guesses (non-admin)
                elif sender in player_emails and game_enabled:
                    if subject_upper.startswith("GUESS"):
                        handled = handle_guess(msg, sender)
                    else:
                        log(f"Ignoring non-GUESS email from player {sender}: {subject[:50]}")
                
                else:
                    log(f"Ignoring email from unknown sender {sender}: {subject[:50]}")
                
                # Mark as read regardless of handling
                mail.store(email_id, "+FLAGS", "\\Seen")
                
            except Exception as exc:
                log(f"Error processing email {email_id}: {exc}")
                # Still mark as read to avoid reprocessing
                try:
                    mail.store(email_id, "+FLAGS", "\\Seen")
                except Exception:
                    pass
        
        mail.logout()
        
    except imaplib.IMAP4.error as exc:
        log(f"IMAP error: {exc}")
    except Exception as exc:
        log(f"Inbox poll failed: {exc}")


# Legacy compatibility - scheduler may still call this
def poll_broadcast_inbox() -> None:
    """Legacy wrapper for backward compatibility with scheduler."""
    poll_inbox()


if __name__ == "__main__":
    poll_inbox()
