"""Narrative API endpoints.

Provides AI-generated narratives with caching and rate limiting.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from utils.logger import create_logger
from web.api.services.narrative_manager import get_narrative_manager

log = create_logger("api_narrative")

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/narrative")
async def get_narrative() -> Dict[str, Any]:
    """Get current narrative, auto-generating if stale.
    
    Returns cached narrative if fresh, or triggers regeneration
    if older than 60 minutes (subject to rate limits and blackout windows).
    
    Returns:
        {
            "subject": "...",
            "headline": "...",
            "body": "...",
            "generated_at": "ISO timestamp",
            "cached": bool,
            "next_refresh_allowed_at": "ISO timestamp" (optional)
        }
    """
    manager = get_narrative_manager()
    result = manager.get_narrative(force_refresh=False)
    
    log(f"Narrative request: cached={result.get('cached', False)}")
    return result


@router.post("/narrative/refresh")
@limiter.limit("4/hour")
async def refresh_narrative(request: Request) -> Dict[str, Any]:
    """Force regenerate the narrative.
    
    Rate limited to 4 requests per hour globally to protect API quotas.
    
    Returns:
        Same schema as GET /narrative, or 429 if rate limited.
    """
    manager = get_narrative_manager()
    result = manager.get_narrative(force_refresh=True)
    
    if result.get("rate_limited"):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": f"Narrative refresh limit reached. Try again in {result.get('retry_after', 0)} seconds.",
                "retry_after": result.get("retry_after", 0),
            },
        )
    
    if result.get("generation_in_progress"):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "generation_in_progress",
                "message": "Another user triggered refresh. Using cached version.",
                "cached_narrative": result,
            },
        )
    
    log(f"Narrative refresh: success={not result.get('cached', True)}")
    return result
