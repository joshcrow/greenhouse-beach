"""Charts API endpoints.

Provides cached chart images for sensor data visualization.
"""

import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from utils.logger import create_logger
from web.api.services.chart_cache import get_chart_cache

log = create_logger("api_charts")

router = APIRouter()

# Valid chart ranges
VALID_RANGES = {"24h": 24, "7d": 168, "30d": 720}


@router.get("/charts/{range}")
async def get_chart(range: str) -> Response:
    """Get a weather chart image for the specified time range.
    
    Args:
        range: Time range - one of "24h", "7d", "30d"
    
    Returns:
        PNG image bytes with appropriate headers
    
    Raises:
        400 if invalid range
        500 if chart generation fails
    """
    if range not in VALID_RANGES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_range",
                "message": f"Invalid range '{range}'. Use one of: {', '.join(VALID_RANGES.keys())}",
            },
        )
    
    hours = VALID_RANGES[range]
    
    log(f"Chart request: range={range} ({hours}h)")
    
    cache = get_chart_cache()
    png_bytes = cache.get_chart(hours)
    
    if not png_bytes:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "generation_failed",
                "message": "Failed to generate chart. Please try again.",
            },
        )
    
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "max-age=300",
            "X-Generated-At": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


@router.get("/history/{range}")
async def get_history_range(range: str):
    """Get historical sensor data for a specific range.
    
    Args:
        range: Time range - one of "24h", "7d", "30d"
    
    Returns:
        { "range": str, "data": [...] }
    """
    if range not in VALID_RANGES:
        raise HTTPException(status_code=400, detail=f"Invalid range: {range}")
    
    hours = VALID_RANGES[range]
    resolution = "hourly" if hours > 48 else "raw"
    
    log(f"History request: range={range}, hours={hours}")
    
    try:
        from chart_generator import _load_sensor_data
        raw_data = _load_sensor_data(hours=hours)
        
        if resolution == "hourly":
            points = _resample_hourly(raw_data)
        else:
            points = raw_data
    except Exception as e:
        log(f"Failed to load history: {e}")
        points = []
    
    return {"range": range, "data": points}


@router.get("/history")
async def get_history(
    hours: int = 24,
    resolution: str = "auto",
    range: str = None,
    metric: str = None,
):
    """Get historical sensor data as JSON.
    
    Args:
        hours: Number of hours of history (default 24, max 720)
        resolution: Data resolution - "raw", "hourly", or "auto"
        range: Alternative to hours - "24h", "7d", or "30d"
        metric: Ignored (for frontend compatibility)
    
    Returns:
        {
            "resolution": "raw" | "hourly",
            "points": [
                {
                    "timestamp": "ISO8601",
                    "interior_temp": float,
                    "exterior_temp": float,
                    "interior_humidity": float,
                    "exterior_humidity": float
                }
            ]
        }
    """
    # Parse range parameter if provided
    if range:
        range_map = {"24h": 24, "7d": 168, "30d": 720}
        hours = range_map.get(range, 24)
    
    # Clamp hours to valid range
    hours = max(1, min(hours, 720))
    
    # Auto-select resolution based on range
    if resolution == "auto":
        resolution = "hourly" if hours > 48 else "raw"
    
    log(f"History request: hours={hours}, resolution={resolution}")
    
    # Load sensor log data
    try:
        from chart_generator import _load_sensor_data
        
        raw_data = _load_sensor_data(hours=hours)
        
        if resolution == "hourly" and hours > 48:
            # Resample to hourly averages
            points = _resample_hourly(raw_data)
        else:
            points = raw_data
        
    except Exception as e:
        log(f"Failed to load history: {e}")
        points = []
    
    return {
        "resolution": resolution,
        "points": points,
    }


def _resample_hourly(data: list) -> list:
    """Resample data to hourly averages.
    
    Args:
        data: List of data points with timestamps
    
    Returns:
        Resampled list with hourly averages
    """
    if not data:
        return []
    
    from datetime import datetime
    from collections import defaultdict
    
    # Group by hour
    hourly = defaultdict(list)
    
    for point in data:
        ts = point.get("timestamp", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            hour_key = dt.strftime("%Y-%m-%dT%H:00:00Z")
            hourly[hour_key].append(point)
        except (ValueError, TypeError):
            continue
    
    # Average each hour
    result = []
    for hour_key in sorted(hourly.keys()):
        points = hourly[hour_key]
        if not points:
            continue
        
        avg_point = {"timestamp": hour_key}
        
        for key in ["interior_temp", "exterior_temp", "interior_humidity", "exterior_humidity"]:
            values = [p.get(key) for p in points if p.get(key) is not None]
            if values:
                avg_point[key] = round(sum(values) / len(values), 1)
        
        result.append(avg_point)
    
    return result
