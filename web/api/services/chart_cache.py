"""Cached chart generation for web API.

Provides in-memory caching for expensive chart generation operations.
Charts are cached for 5 minutes to avoid repeated matplotlib rendering.
"""

import time
from dataclasses import dataclass
from typing import Dict, Optional

from utils.logger import create_logger

log = create_logger("chart_cache")

# Cache TTL in seconds (5 minutes)
CACHE_TTL_SECONDS = 300


@dataclass
class CachedChart:
    """Cached chart data with timestamp."""
    
    png_bytes: bytes
    generated_at: float  # time.time()
    hours: int


class ChartCache:
    """In-memory cache for chart images."""
    
    def __init__(self):
        self._cache: Dict[str, CachedChart] = {}
    
    def get_chart(self, hours: int) -> Optional[bytes]:
        """Get chart PNG, generating if stale or missing.
        
        Args:
            hours: Time range in hours (24, 168, or 720)
        
        Returns:
            PNG bytes, or None if generation fails
        """
        cache_key = f"{hours}h"
        
        # Check cache
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached.generated_at) < CACHE_TTL_SECONDS:
            log(f"Cache hit for {cache_key}")
            return cached.png_bytes
        
        # Generate fresh chart
        log(f"Generating {cache_key} chart...")
        
        try:
            from chart_generator import generate_weather_dashboard
            png_bytes = generate_weather_dashboard(hours=hours)
            
            if png_bytes:
                self._cache[cache_key] = CachedChart(
                    png_bytes=png_bytes,
                    generated_at=time.time(),
                    hours=hours,
                )
                log(f"Generated and cached {cache_key} chart ({len(png_bytes)} bytes)")
                return png_bytes
            else:
                log(f"Chart generation returned no data for {cache_key}")
                return None
                
        except Exception as e:
            log(f"Chart generation failed for {cache_key}: {e}")
            
            # Return stale cache if available
            if cached:
                log(f"Returning stale cache for {cache_key}")
                return cached.png_bytes
            
            return None
    
    def invalidate(self, hours: Optional[int] = None) -> None:
        """Invalidate cached charts.
        
        Args:
            hours: Specific range to invalidate, or None for all
        """
        if hours is not None:
            cache_key = f"{hours}h"
            if cache_key in self._cache:
                del self._cache[cache_key]
                log(f"Invalidated cache for {cache_key}")
        else:
            self._cache.clear()
            log("Invalidated all chart caches")


# Singleton instance
_chart_cache: Optional[ChartCache] = None


def get_chart_cache() -> ChartCache:
    """Get the singleton ChartCache instance."""
    global _chart_cache
    if _chart_cache is None:
        _chart_cache = ChartCache()
    return _chart_cache
