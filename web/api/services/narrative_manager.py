"""Narrative caching and rate-limiting for web API.

Responsibilities:
- Cache current narrative in memory + disk
- Enforce rate limits (4/hour)
- Prevent concurrent generation (file lock)
- Blackout window around daily email
"""

import fcntl
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from utils.io import atomic_read_json, atomic_write_json
from utils.logger import create_logger
from app.config import settings

log = create_logger("narrative_manager")

# Paths
CACHE_PATH = "/app/data/narrative_cache.json"
LOCK_PATH = "/app/data/narrative_generation.lock"
RATE_LIMIT_PATH = "/app/data/narrative_rate_limit.json"

# Configuration
MAX_AGE_MINUTES = 60
MAX_GENERATIONS_PER_HOUR = 4
BLACKOUT_BEFORE_EMAIL_MINUTES = 30
EMAIL_HOUR = 7  # 07:00 local time


@dataclass
class CachedNarrative:
    """Cached narrative data with metadata."""
    
    subject: str
    headline: str
    body: str
    generated_at: datetime
    cached: bool = False
    
    def is_stale(self) -> bool:
        """Check if narrative is older than MAX_AGE_MINUTES."""
        if self.generated_at.tzinfo is None:
            now = datetime.utcnow()
        else:
            now = datetime.now(timezone.utc)
            if self.generated_at.tzinfo is None:
                self.generated_at = self.generated_at.replace(tzinfo=timezone.utc)
        
        age = now - self.generated_at.replace(tzinfo=None) if self.generated_at.tzinfo else now - self.generated_at
        return age > timedelta(minutes=MAX_AGE_MINUTES)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to API response dict."""
        generated_at_str = self.generated_at.isoformat()
        if not generated_at_str.endswith("Z") and "+" not in generated_at_str:
            generated_at_str += "Z"
        
        return {
            "subject": self.subject,
            "headline": self.headline,
            "body": self.body,
            "generated_at": generated_at_str,
            "cached": self.cached,
        }


class NarrativeManager:
    """Thread-safe narrative cache with rate limiting."""
    
    def __init__(self):
        self._cache: Optional[CachedNarrative] = None
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load cached narrative from disk."""
        data = atomic_read_json(CACHE_PATH, default=None)
        if data and "generated_at" in data:
            try:
                generated_at_str = data["generated_at"]
                if generated_at_str.endswith("Z"):
                    generated_at_str = generated_at_str[:-1]
                if "+" in generated_at_str:
                    generated_at_str = generated_at_str.split("+")[0]
                
                self._cache = CachedNarrative(
                    subject=data.get("subject", ""),
                    headline=data.get("headline", ""),
                    body=data.get("body", ""),
                    generated_at=datetime.fromisoformat(generated_at_str),
                )
                log(f"Loaded cached narrative from {self._cache.generated_at}")
            except Exception as e:
                log(f"Failed to load cache: {e}")
    
    def _save_cache(self, narrative: CachedNarrative) -> None:
        """Persist narrative to disk."""
        atomic_write_json(CACHE_PATH, narrative.to_dict())
    
    def _is_blackout_window(self) -> bool:
        """Check if we're within blackout period before daily email."""
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(settings.tz if settings else "America/New_York")
            now = datetime.now(tz)
        except Exception:
            now = datetime.now()
        
        email_time = now.replace(hour=EMAIL_HOUR, minute=0, second=0, microsecond=0)
        
        # If email already sent today, check tomorrow's window
        if now.hour >= EMAIL_HOUR:
            email_time += timedelta(days=1)
        
        time_until_email = email_time - now
        return time_until_email < timedelta(minutes=BLACKOUT_BEFORE_EMAIL_MINUTES)
    
    def _check_rate_limit(self) -> tuple[bool, int]:
        """Check if rate limit allows generation.
        
        Returns:
            (allowed: bool, seconds_until_allowed: int)
        """
        data = atomic_read_json(RATE_LIMIT_PATH, default={"timestamps": []})
        timestamps = data.get("timestamps", [])
        
        # Filter to last hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        recent = []
        for ts in timestamps:
            try:
                ts_clean = ts.replace("Z", "") if ts.endswith("Z") else ts
                ts_dt = datetime.fromisoformat(ts_clean)
                if ts_dt > cutoff:
                    recent.append(ts)
            except (ValueError, TypeError):
                continue
        
        if len(recent) >= MAX_GENERATIONS_PER_HOUR:
            # Calculate when oldest will expire
            try:
                oldest_str = recent[0].replace("Z", "") if recent[0].endswith("Z") else recent[0]
                oldest = datetime.fromisoformat(oldest_str)
                seconds_until = int((oldest + timedelta(hours=1) - datetime.utcnow()).total_seconds())
                return False, max(0, seconds_until)
            except Exception:
                return False, 3600  # Default to 1 hour
        
        return True, 0
    
    def _record_generation(self) -> None:
        """Record a generation timestamp for rate limiting."""
        data = atomic_read_json(RATE_LIMIT_PATH, default={"timestamps": []})
        timestamps = data.get("timestamps", [])
        timestamps.append(datetime.utcnow().isoformat() + "Z")
        
        # Keep only last hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        filtered = []
        for ts in timestamps:
            try:
                ts_clean = ts.replace("Z", "") if ts.endswith("Z") else ts
                ts_dt = datetime.fromisoformat(ts_clean)
                if ts_dt > cutoff:
                    filtered.append(ts)
            except (ValueError, TypeError):
                continue
        
        atomic_write_json(RATE_LIMIT_PATH, {"timestamps": filtered})
    
    def get_narrative(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get current narrative, regenerating if stale.
        
        Args:
            force_refresh: If True, attempt regeneration regardless of age
        
        Returns:
            Narrative dict with metadata
        """
        # Check if refresh is needed/allowed
        need_refresh = force_refresh or (self._cache is None) or self._cache.is_stale()
        
        if need_refresh:
            if self._is_blackout_window():
                log("Blackout window active, using cache")
                if self._cache:
                    result = self._cache.to_dict()
                    result["cached"] = True
                    result["blackout"] = True
                    return result
                return self._fallback_narrative()
            
            allowed, retry_after = self._check_rate_limit()
            if not allowed:
                log(f"Rate limited, retry in {retry_after}s")
                if self._cache:
                    result = self._cache.to_dict()
                    result["cached"] = True
                    result["rate_limited"] = True
                    result["retry_after"] = retry_after
                    return result
                return self._fallback_narrative()
            
            # Attempt generation with file lock
            return self._generate_with_lock()
        
        # Return cached version
        if self._cache:
            return self._cache.to_dict()
        return self._fallback_narrative()
    
    def _generate_with_lock(self) -> Dict[str, Any]:
        """Generate narrative with file-based lock."""
        # Ensure lock directory exists
        os.makedirs(os.path.dirname(LOCK_PATH) or ".", exist_ok=True)
        
        try:
            lock_fd = open(LOCK_PATH, "w")
            # Non-blocking lock attempt
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, BlockingIOError, OSError):
            log("Generation already in progress")
            if self._cache:
                result = self._cache.to_dict()
                result["cached"] = True
                result["generation_in_progress"] = True
                return result
            return self._fallback_narrative()
        
        try:
            # Do the actual generation
            narrative = self._generate_narrative()
            self._cache = narrative
            self._save_cache(narrative)
            self._record_generation()
            return narrative.to_dict()
        except Exception as e:
            log(f"Generation failed: {e}")
            if self._cache:
                result = self._cache.to_dict()
                result["cached"] = True
                result["error"] = str(e)
                return result
            return self._fallback_narrative()
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass
    
    def _generate_narrative(self) -> CachedNarrative:
        """Generate fresh narrative using narrator module."""
        log("Generating fresh narrative...")
        
        try:
            import narrator
            from publisher import load_latest_sensor_snapshot
            
            # Load current sensor data
            snapshot = load_latest_sensor_snapshot()
            sensor_data = snapshot.get("sensors", {})
            
            # Call generate_narrative_only if available, otherwise use generate_update
            if hasattr(narrator, "generate_narrative_only"):
                subject, headline, body = narrator.generate_narrative_only(sensor_data)
            else:
                # Fallback to full generate_update
                subject, headline, body_html, body_plain, _ = narrator.generate_update(
                    sensor_data, is_weekly=False, test_mode=True
                )
                body = body_plain
            
            return CachedNarrative(
                subject=subject,
                headline=headline,
                body=body,
                generated_at=datetime.utcnow(),
                cached=False,
            )
        except Exception as e:
            log(f"Narrative generation failed: {e}")
            raise
    
    def _fallback_narrative(self) -> Dict[str, Any]:
        """Return fallback when no cache and can't generate."""
        return {
            "subject": "The Captain is quiet",
            "headline": "No update available",
            "body": "The Captain hasn't filed a report yet. Check back after the morning Gazette.",
            "generated_at": None,
            "cached": True,
            "fallback": True,
        }


# Singleton instance
_manager: Optional[NarrativeManager] = None


def get_narrative_manager() -> NarrativeManager:
    """Get the singleton NarrativeManager instance."""
    global _manager
    if _manager is None:
        _manager = NarrativeManager()
    return _manager
