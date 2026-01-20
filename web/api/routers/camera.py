"""Camera and timelapse API endpoints.

Provides access to greenhouse camera images and timelapse videos.
Supports on-demand capture requests via MQTT.
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from utils.logger import create_logger
from app.config import settings

log = create_logger("api_camera")

router = APIRouter()

# Track last capture request time for rate limiting
_last_capture_request = 0.0
CAPTURE_RATE_LIMIT_SECONDS = 15


class CaptureResponse(BaseModel):
    success: bool
    message: str
    estimated_delay_seconds: int = 5


def get_latest_image_path() -> Optional[Path]:
    """Find the most recent camera image in the archive.
    
    Checks both regular archive (daylight) and _night archive.
    
    Returns:
        Path to the latest image, or None if not found
    """
    archive_path = Path(settings.archive_path if settings else "/app/data/archive")
    
    if not archive_path.exists():
        return None
    
    def find_latest_in_archive(base_path: Path) -> Optional[tuple]:
        """Find latest image and its mtime in an archive path."""
        if not base_path.exists():
            return None
        
        try:
            # Get year directories (sorted descending)
            years = sorted(
                [d for d in base_path.iterdir() if d.is_dir() and d.name.isdigit()],
                key=lambda x: x.name,
                reverse=True,
            )
            
            for year_dir in years:
                months = sorted(
                    [d for d in year_dir.iterdir() if d.is_dir() and d.name.isdigit()],
                    key=lambda x: x.name,
                    reverse=True,
                )
                
                for month_dir in months:
                    days = sorted(
                        [d for d in month_dir.iterdir() if d.is_dir() and d.name.isdigit()],
                        key=lambda x: x.name,
                        reverse=True,
                    )
                    
                    for day_dir in days:
                        images = sorted(
                            [
                                f for f in day_dir.iterdir()
                                if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png")
                            ],
                            key=lambda x: x.name,
                            reverse=True,
                        )
                        
                        if images:
                            return (images[0], images[0].stat().st_mtime)
        except Exception:
            pass
        return None
    
    try:
        # Check both regular archive and _night archive
        day_result = find_latest_in_archive(archive_path)
        night_result = find_latest_in_archive(archive_path / "_night")
        
        # Return the most recent of the two
        if day_result and night_result:
            return day_result[0] if day_result[1] > night_result[1] else night_result[0]
        elif day_result:
            return day_result[0]
        elif night_result:
            return night_result[0]
    
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
    
    # Extract capture time from filename (format: img_camera_YYYYMMDD_HHMMSS.jpg)
    # Filename timestamps are in UTC
    import re
    capture_time_str = ""
    try:
        match = re.search(r'(\d{8})_(\d{6})', image_path.name)
        if match:
            date_str, time_str = match.groups()
            # Parse as UTC timestamp
            capture_time_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}T{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}Z"
        else:
            # Fallback to mtime if filename doesn't match pattern
            from datetime import timezone
            capture_time = datetime.fromtimestamp(image_path.stat().st_mtime, tz=timezone.utc)
            capture_time_str = capture_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    
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


@router.post("/camera/capture")
async def request_camera_capture() -> CaptureResponse:
    """Request an on-demand camera capture.
    
    Publishes a capture request to MQTT. The camera Pi will capture
    a fresh 4K image and publish it back. The new image should be
    available within ~5 seconds.
    
    Rate limited to 1 request per 15 seconds.
    
    Returns:
        CaptureResponse with success status and estimated delay
    """
    global _last_capture_request
    
    # Rate limiting
    now = time.time()
    if now - _last_capture_request < CAPTURE_RATE_LIMIT_SECONDS:
        wait_time = int(CAPTURE_RATE_LIMIT_SECONDS - (now - _last_capture_request))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited. Please wait {wait_time} seconds.",
        )
    
    try:
        import paho.mqtt.client as mqtt
        
        mqtt_host = settings.mqtt_host if settings else os.getenv("MQTT_HOST", "mosquitto")
        mqtt_port = settings.mqtt_port if settings else int(os.getenv("MQTT_PORT", "1883"))
        mqtt_user = settings.mqtt_username if settings else os.getenv("MQTT_USERNAME")
        mqtt_pass = settings.mqtt_password if settings else os.getenv("MQTT_PASSWORD")
        
        # Track connection status
        connected = [False]
        
        def on_connect(client, userdata, flags, rc):
            connected[0] = (rc == 0)
        
        client = mqtt.Client()
        client.on_connect = on_connect
        
        if mqtt_user and mqtt_pass:
            client.username_pw_set(mqtt_user, mqtt_pass)
        
        client.connect(mqtt_host, mqtt_port, keepalive=10)
        client.loop_start()
        
        # Wait for connection (up to 3 seconds)
        for _ in range(30):
            if connected[0]:
                break
            time.sleep(0.1)
        
        if not connected[0]:
            client.loop_stop()
            raise HTTPException(status_code=503, detail="Failed to connect to MQTT broker")
        
        # Publish capture request
        result = client.publish("greenhouse/camera/capture", "refresh", qos=1)
        result.wait_for_publish(timeout=5)
        
        client.loop_stop()
        client.disconnect()
        
        if result.is_published():
            _last_capture_request = now
            log("On-demand capture request sent via MQTT")
            return CaptureResponse(
                success=True,
                message="Capture request sent. New image will be available in ~5 seconds.",
                estimated_delay_seconds=5,
            )
        else:
            log("Failed to publish capture request")
            raise HTTPException(
                status_code=503,
                detail="Failed to send capture request",
            )
    
    except ImportError:
        log("paho-mqtt not installed")
        raise HTTPException(
            status_code=503,
            detail="MQTT client not available",
        )
    except Exception as e:
        log(f"Error sending capture request: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to send capture request: {str(e)}",
        )
