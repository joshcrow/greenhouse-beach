#!/usr/bin/env python3
"""Backfill riddle scores from old email guesses.

Scans the Gmail inbox for past GUESS emails and retroactively scores them.
This is a one-time migration script.

Usage:
    python scripts/backfill_riddle_scores.py --dry-run  # Preview what would be scored
    python scripts/backfill_riddle_scores.py            # Actually process and score
"""

import argparse
import email
import imaplib
import json
import os
import re
import sys
from datetime import datetime
from email.header import decode_header
from typing import Any, Dict, List, Optional, Tuple

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
sys.path.insert(0, os.path.dirname(script_dir))  # Parent for app.config

from utils.io import atomic_write_json, atomic_read_json
from utils.logger import create_logger

log = create_logger("backfill_scores")

# Import game modules
import narrator
import scorekeeper


def _get_settings():
    try:
        from app.config import settings
        return settings
    except Exception:
        return None


def decode_email_subject(subject) -> str:
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
    from_header = msg.get("From", "")
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].lower().strip()
    return from_header.lower().strip()


def parse_email_timestamp(msg) -> Optional[datetime]:
    from email.utils import parsedate_to_datetime
    date_header = msg.get("Date")
    if not date_header:
        return None
    try:
        return parsedate_to_datetime(date_header).replace(tzinfo=None)
    except Exception:
        return None


def parse_guess_subject(subject: str) -> Optional[Tuple[str, str]]:
    match = re.search(
        r"GUESS\s*\[(\d{4}-\d{2}-\d{2})\]\s*:?\s*(.*)",
        subject,
        re.IGNORECASE
    )
    if match:
        return match.group(1), match.group(2).strip()
    return None


def extract_guess_text(body: str) -> str:
    if not body:
        return ""
    for marker in ["\nOn ", "\n>", "\n--", "\nSent from", "\n___"]:
        if marker in body:
            body = body.split(marker)[0]
    lines = [l.strip() for l in body.strip().split("\n") if l.strip()]
    return " ".join(lines)[:200].strip()


def load_riddle_history() -> Dict[str, Dict[str, str]]:
    """Load riddle history indexed by date."""
    history = atomic_read_json("/app/data/riddle_history.json", default=[])
    # Index by date (use last entry for duplicate dates)
    by_date = {}
    for entry in history:
        by_date[entry["date"]] = entry
    return by_date


def scan_inbox_for_guesses(dry_run: bool = True) -> List[Dict[str, Any]]:
    """Scan inbox for all GUESS emails."""
    cfg = _get_settings()
    if not cfg:
        log("ERROR: Settings not available")
        return []
    
    imap_server = "imap.gmail.com"
    email_addr = cfg.smtp_user
    password = cfg.smtp_password
    
    if not email_addr or not password:
        log("ERROR: SMTP credentials not configured")
        return []
    
    # Get family emails
    player_emails = [e.lower() for e in cfg.smtp_recipients]
    
    # Load riddle history
    riddle_history = load_riddle_history()
    
    guesses = []
    
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_addr, password)
        mail.select("inbox")
        
        # Search for emails with GUESS in subject
        _, data = mail.search(None, '(SUBJECT "GUESS")')
        email_ids = data[0].split()
        
        log(f"Found {len(email_ids)} emails with GUESS in subject")
        
        for email_id in email_ids:
            try:
                _, msg_data = mail.fetch(email_id, "(RFC822)")
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                sender = extract_sender_email(msg)
                subject = decode_email_subject(msg.get("Subject", ""))
                body = get_email_body(msg).strip()
                timestamp = parse_email_timestamp(msg)
                
                # Only process family emails
                if sender not in player_emails:
                    log(f"  Skipping non-player: {sender}")
                    continue
                
                # Parse guess
                parsed = parse_guess_subject(subject)
                if parsed:
                    date_id, guess_text = parsed
                    if not guess_text:
                        guess_text = extract_guess_text(body)
                else:
                    # No structured format - skip (can't determine date)
                    log(f"  Skipping unparseable subject: {subject[:50]}")
                    continue
                
                if not guess_text:
                    log(f"  Skipping empty guess from {sender}")
                    continue
                
                # Get riddle for that date
                riddle_entry = riddle_history.get(date_id)
                if not riddle_entry:
                    log(f"  Skipping - no riddle found for date {date_id}")
                    continue
                
                guess_info = {
                    "sender": sender,
                    "date_id": date_id,
                    "guess_text": guess_text,
                    "timestamp": timestamp.isoformat() if timestamp else None,
                    "riddle": riddle_entry.get("riddle", ""),
                    "correct_answer": riddle_entry.get("answer", ""),
                }
                
                guesses.append(guess_info)
                log(f"  Found: {sender} -> {date_id}: '{guess_text[:30]}...'")
                
            except Exception as exc:
                log(f"  Error processing email {email_id}: {exc}")
        
        mail.logout()
        
    except Exception as exc:
        log(f"IMAP error: {exc}")
    
    return guesses


def score_guesses(guesses: List[Dict[str, Any]], dry_run: bool = True) -> None:
    """Score the guesses using AI judging."""
    log(f"\n{'DRY RUN - ' if dry_run else ''}Scoring {len(guesses)} guesses...")
    
    # Group by date to handle first-solver correctly
    by_date = {}
    for g in guesses:
        date_id = g["date_id"]
        if date_id not in by_date:
            by_date[date_id] = []
        by_date[date_id].append(g)
    
    # Sort each date's guesses by timestamp
    for date_id in by_date:
        by_date[date_id].sort(key=lambda x: x["timestamp"] or "9999")
    
    results = []
    
    for date_id in sorted(by_date.keys()):
        date_guesses = by_date[date_id]
        log(f"\n=== {date_id} ({len(date_guesses)} guesses) ===")
        
        # Track solvers for this date
        solvers_this_date = set()
        first_solver = None
        
        for g in date_guesses:
            sender = g["sender"]
            guess_text = g["guess_text"]
            correct_answer = g["correct_answer"]
            riddle_text = g["riddle"]
            
            # Judge the guess
            judgment = narrator.judge_riddle(
                user_guess=guess_text,
                correct_answer=correct_answer,
                riddle_text=riddle_text
            )
            
            is_correct = judgment["correct"]
            
            if is_correct:
                if sender in solvers_this_date:
                    log(f"  {sender}: '{guess_text[:20]}' -> CORRECT (duplicate)")
                    continue
                
                is_first = first_solver is None
                if is_first:
                    first_solver = sender
                    points = 2
                else:
                    points = 1
                
                solvers_this_date.add(sender)
                
                result = {
                    "sender": sender,
                    "date": date_id,
                    "guess": guess_text,
                    "correct": True,
                    "is_first": is_first,
                    "points": points,
                }
                results.append(result)
                
                log(f"  {sender}: '{guess_text[:20]}' -> CORRECT{'(FIRST!)' if is_first else ''} +{points} pts")
                
                if not dry_run:
                    # Actually update scores
                    scores = atomic_read_json("/app/data/riddle_scores.json", default={"players": {}})
                    players = scores.setdefault("players", {})
                    
                    if sender not in players:
                        players[sender] = {
                            "display_name": sender.split("@")[0].lower(),
                            "points": 0,
                            "wins": 0,
                            "last_played": date_id
                        }
                    
                    player = players[sender]
                    player["points"] = player.get("points", 0) + points
                    if is_first:
                        player["wins"] = player.get("wins", 0) + 1
                    player["last_played"] = date_id
                    
                    atomic_write_json("/app/data/riddle_scores.json", scores)
            else:
                log(f"  {sender}: '{guess_text[:20]}' -> wrong")
    
    # Summary
    log(f"\n=== SUMMARY ===")
    log(f"Total correct guesses: {len(results)}")
    
    # Points by player
    player_points = {}
    player_wins = {}
    for r in results:
        sender = r["sender"]
        player_points[sender] = player_points.get(sender, 0) + r["points"]
        if r["is_first"]:
            player_wins[sender] = player_wins.get(sender, 0) + 1
    
    for player in sorted(player_points.keys(), key=lambda x: -player_points[x]):
        wins = player_wins.get(player, 0)
        log(f"  {player}: {player_points[player]} pts, {wins} wins")


def main():
    parser = argparse.ArgumentParser(description="Backfill riddle scores from old emails")
    parser.add_argument("--dry-run", action="store_true", help="Preview without actually scoring")
    args = parser.parse_args()
    
    log(f"Starting backfill {'(DRY RUN)' if args.dry_run else '(LIVE)'}")
    
    guesses = scan_inbox_for_guesses(dry_run=args.dry_run)
    
    if guesses:
        score_guesses(guesses, dry_run=args.dry_run)
    else:
        log("No guesses found to process")


if __name__ == "__main__":
    main()
