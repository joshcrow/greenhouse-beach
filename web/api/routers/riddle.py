"""Riddle game API endpoints.

Provides riddle questions, guess submission, and leaderboard.
"""

import html
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from utils.io import atomic_read_json
from utils.logger import create_logger
from app.config import settings

log = create_logger("api_riddle")

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class GuessRequest(BaseModel):
    """Request body for riddle guess submission."""
    guess: str = Field(..., min_length=1, max_length=200)
    
    @field_validator("guess")
    @classmethod
    def sanitize_guess(cls, v: str) -> str:
        """Strip HTML tags and normalize whitespace."""
        # Remove HTML tags
        v = re.sub(r"<[^>]+>", "", v)
        # Escape remaining HTML entities
        v = html.escape(v)
        # Normalize whitespace
        v = " ".join(v.split())
        return v.strip()


def get_user_email(request: Request) -> str:
    """Extract user email from Cloudflare Access JWT.
    
    Cloudflare Access sits in front of this service and validates JWTs.
    We trust the Cf-Access-Authenticated-User-Email header which Cloudflare
    sets after JWT validation. This is safe because:
    1. Cloudflare Tunnel only allows traffic from Cloudflare's edge
    2. Cloudflare Access validates the JWT before setting this header
    3. The header cannot be spoofed by end users through Cloudflare
    
    Args:
        request: FastAPI request object
    
    Returns:
        User email or "anonymous" if not authenticated
    """
    # Primary: Use Cloudflare's validated email header (set after JWT verification)
    cf_email = request.headers.get("Cf-Access-Authenticated-User-Email")
    if cf_email:
        return cf_email.lower().strip()
    
    # Fallback: Parse JWT claims (for local development without Cloudflare)
    # Note: In production, Cloudflare validates the JWT before requests reach us
    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if token:
        try:
            from jose import jwt
            # We only use unverified claims as a fallback for dev
            # In production, Cloudflare has already verified the JWT
            claims = jwt.get_unverified_claims(token)
            return claims.get("email", "anonymous")
        except Exception:
            pass
    
    return "anonymous"


@router.get("/riddle/yesterday")
async def get_yesterday_riddle() -> Dict[str, Any]:
    """Get yesterday's riddle with the answer revealed.
    
    Returns:
        {
            "question": "...",
            "answer": "...",
            "date": "YYYY-MM-DD"
        }
    
    Raises:
        404 if no yesterday riddle is available
    """
    from datetime import datetime, timedelta
    
    from pathlib import Path
    history_path = Path(settings.data_dir) / "riddle_history.json" if settings else Path("/app/data/riddle_history.json")
    history = atomic_read_json(history_path, default=[])
    
    if not history:
        raise HTTPException(status_code=404, detail={"error": "no_history", "message": "No riddle history available."})
    
    # Get yesterday's date
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Find yesterday's riddle
    yesterday_riddle = None
    for riddle in reversed(history):
        if riddle.get("date") == yesterday:
            yesterday_riddle = riddle
            break
    
    # If no exact match for yesterday, get the most recent that's not today
    if not yesterday_riddle:
        today = datetime.now().strftime("%Y-%m-%d")
        for riddle in reversed(history):
            if riddle.get("date") != today:
                yesterday_riddle = riddle
                break
    
    if not yesterday_riddle:
        raise HTTPException(status_code=404, detail={"error": "no_yesterday", "message": "No previous riddle available."})
    
    return {
        "question": yesterday_riddle.get("riddle", ""),
        "answer": yesterday_riddle.get("answer", ""),
        "date": yesterday_riddle.get("date", ""),
    }


@router.get("/riddle")
async def get_riddle() -> Dict[str, Any]:
    """Get the current active riddle.
    
    Returns:
        {
            "question": "...",
            "date": "YYYY-MM-DD",
            "active": true
        }
    
    Raises:
        404 if no riddle is available
    """
    riddle_path = settings.riddle_state_path if settings else "/app/data/riddle_state.json"
    
    riddle_state = atomic_read_json(riddle_path, default=None)
    
    # State file uses "riddle" key, not "question"
    riddle_text = riddle_state.get("riddle") or riddle_state.get("question") if riddle_state else None
    
    if not riddle_text:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_riddle",
                "message": "No riddle available. Check back after the morning Gazette.",
            },
        )
    
    return {
        "question": riddle_text,
        "date": riddle_state.get("date", ""),
        "active": True,
    }


@router.post("/riddle/guess")
@limiter.limit("10/minute")  # Prevent guess brute-forcing and AI API abuse
async def submit_guess(request: Request, body: GuessRequest) -> Dict[str, Any]:
    """Submit a guess for the current riddle.
    
    Rate limited to 10 guesses per minute per IP to prevent brute-forcing
    and protect Gemini API costs.
    
    Args:
        body: GuessRequest with sanitized guess string
    
    Returns:
        {
            "correct": bool,
            "points": int (if correct),
            "is_first": bool (if correct),
            "rank": int (if correct),
            "message": "..."
        }
    """
    user_email = get_user_email(request)
    guess = body.guess
    
    log(f"Riddle guess from {user_email}: '{guess[:30]}...'")
    
    # Load current riddle state
    riddle_path = settings.riddle_state_path if settings else "/app/data/riddle_state.json"
    riddle_state = atomic_read_json(riddle_path, default=None)
    
    # Check for riddle (supports both "question" and "riddle" keys)
    riddle_text = riddle_state.get("question") or riddle_state.get("riddle") if riddle_state else None
    if not riddle_text:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_riddle",
                "message": "No riddle available to guess.",
            },
        )
    
    riddle_date = riddle_state.get("date", "")
    
    # Import scorekeeper and narrator for judging
    try:
        import scorekeeper
        import narrator
    except ImportError as e:
        log(f"Failed to import game modules: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Riddle game temporarily unavailable.",
            },
        )
    
    # Judge the guess
    try:
        is_correct, feedback = narrator.judge_riddle(
            riddle_text,
            riddle_state.get("answer", ""),
            guess,
        )
    except Exception as e:
        log(f"Judge riddle failed: {e}")
        # Fallback to simple string matching
        correct_answer = riddle_state.get("answer", "").lower().strip()
        is_correct = guess.lower().strip() == correct_answer
        feedback = "Correct!" if is_correct else "Not quite. Try again!"
    
    # Record the attempt
    try:
        result = scorekeeper.record_attempt(
            user_email=user_email,
            guess_is_correct=is_correct,
            riddle_date=riddle_date,
        )
    except Exception as e:
        log(f"Record attempt failed: {e}")
        result = {"status": "correct" if is_correct else "wrong"}
    
    # Build response
    if result.get("status") == "already_solved":
        return {
            "correct": None,
            "already_solved": True,
            "message": "Ye already cracked this one. Save yer ink for tomorrow.",
        }
    
    if is_correct:
        return {
            "correct": True,
            "points": result.get("points", 1),
            "is_first": result.get("is_first", False),
            "rank": result.get("rank", 0),
            "message": feedback,
        }
    
    return {
        "correct": False,
        "message": feedback,
    }


@router.get("/leaderboard")
async def get_leaderboard() -> Dict[str, Any]:
    """Get the riddle game leaderboard.
    
    Returns:
        {
            "season_start": "YYYY-MM-DD",
            "players": [
                { "display_name": "...", "points": int, "wins": int }
            ]
        }
    """
    try:
        import scorekeeper
        leaderboard = scorekeeper.get_leaderboard()
    except Exception as e:
        log(f"Get leaderboard failed: {e}")
        leaderboard = []
    
    # Format for API response
    players = []
    for entry in leaderboard[:10]:  # Top 10
        players.append({
            "display_name": entry.get("display_name", entry.get("email", "unknown")),
            "points": entry.get("points", 0),
            "wins": entry.get("wins", 0),
        })
    
    return {
        "season_start": "2026-01-01",  # TODO: Track actual season start
        "players": players,
    }


@router.get("/riddle/stats")
async def get_player_stats(request: Request) -> Dict[str, Any]:
    """Get stats for the current user.
    
    Returns:
        {
            "display_name": "...",
            "points": int,
            "wins": int,
            "rank": int,
            "last_played": "YYYY-MM-DD"
        }
    """
    user_email = get_user_email(request)
    
    if user_email == "anonymous":
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Authentication required to view stats.",
            },
        )
    
    try:
        import scorekeeper
        stats = scorekeeper.get_player_stats(user_email)
    except Exception as e:
        log(f"Get player stats failed: {e}")
        stats = {}
    
    if not stats:
        return {
            "display_name": user_email.split("@")[0],
            "points": 0,
            "wins": 0,
            "rank": 0,
            "last_played": None,
        }
    
    return {
        "display_name": stats.get("display_name", user_email.split("@")[0]),
        "points": stats.get("points", 0),
        "wins": stats.get("wins", 0),
        "rank": stats.get("rank", 0),
        "last_played": stats.get("last_played"),
    }
