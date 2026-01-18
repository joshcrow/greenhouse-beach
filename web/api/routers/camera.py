"""Camera and timelapse API endpoints.

Provides access to greenhouse camera images and timelapse videos.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from utils.logger import create_logger
from app.config import settings

log = create_logger("api_camera")

router = APIRouter()


def get_latest_image_path() -> Optional[Path]:
    """Find the most recent camera image in the archive.
    
    Returns:
        Path to the latest image, or None if not found
    """
    archive_path = Path(settings.archive_path if settings else "/app/data/archive")
    
    if not archive_path.exists():
        return None
    
    # Walk backwards through date directories to find latest
    try:
        # Get year directories (sorted descending)
        years = sorted(
            [d for d in archive_path.iterdir() if d.is_dir() and d.name.isdigit()],
            key=lambda x: x.name,
            reverse=True,
        )
        
        for year_dir in years:
            # Get month directories
            months = sorted(
                [d for d in year_dir.iterdir() if d.is_dir() and d.name.isdigit()],
                key=lambda x: x.name,
                reverse=True,
            )
            
            for month_dir in months:
                # Get day directories
                days = sorted(
                    [d for d in month_dir.iterdir() if d.is_dir() and d.name.isdigit()],
                    key=lambda x: x.name,
                    reverse=True,
                )
                
                for day_dir in days:
                    # Get image files (jpg, jpeg, png)
                    images = sorted(
                        [
                            f for f in day_dir.iterdir()
                            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png")
                        ],
                        key=lambda x: x.name,
                        reverse=True,
                    )
                    
                    if images:
                        return images[0]
    
    except Exception as e:
        log(f"Error finding latest image: {e}")
    
    return None


@router.get("/camera/latest")
async def get_latest_camera_image() -> Response:
    """Get the most recent camera image.
    
    Returns:
        JPEG image with capture time in header
    
    Raises:
        404 if no images available
    """
    image_path = get_latest_image_path()
    
    if not image_path or not image_path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_image",
                "message": "No camera images available.",
            },
        )
    
    # Extract capture time from filename or mtime
    try:
        capture_time = datetime.fromtimestamp(image_path.stat().st_mtime)
        capture_time_str = capture_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        capture_time_str = ""
    
    log(f"Serving latest image: {image_path.name}")
    
    return FileResponse(
        path=str(image_path),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Capture-Time": capture_time_str,
        },
    )


@router.get("/timelapses")
async def get_timelapse_list() -> Dict[str, Any]:
    """Get available timelapse videos.
    
    Returns:
        {
            "daily": "/static/timelapses/daily_YYYY-MM-DD.gif" | null,
            "weekly": "/static/timelapses/weekly_YYYY-Www.mp4" | null,
            "monthly": "/static/timelapses/monthly_YYYY-MM.mp4" | null
        }
    """
    timelapse_dir = Path("/app/data/www/timelapses")
    
    result = {
        "daily": None,
        "weekly": None,
        "monthly": None,
    }
    
    if not timelapse_dir.exists():
        return result
    
    try:
        files = list(timelapse_dir.iterdir())
        
        # Find most recent of each type
        daily_files = sorted(
            [f for f in files if f.name.startswith("daily_") and f.suffix in (".gif", ".mp4")],
            key=lambda x: x.name,
            reverse=True,
        )
        weekly_files = sorted(
            [f for f in files if f.name.startswith("weekly_") and f.suffix == ".mp4"],
            key=lambda x: x.name,
            reverse=True,
        )
        monthly_files = sorted(
            [f for f in files if f.name.startswith("monthly_") and f.suffix == ".mp4"],
            key=lambda x: x.name,
            reverse=True,
        )
        
        if daily_files:
            result["daily"] = f"/static/timelapses/{daily_files[0].name}"
        if weekly_files:
            result["weekly"] = f"/static/timelapses/{weekly_files[0].name}"
        if monthly_files:
            result["monthly"] = f"/static/timelapses/{monthly_files[0].name}"
    
    except Exception as e:
        log(f"Error listing timelapses: {e}")
    
    return result
