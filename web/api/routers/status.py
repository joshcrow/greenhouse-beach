"""Sensor status API endpoints.

Provides real-time sensor data with staleness detection,
including WebSocket support for live updates.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.io import atomic_read_json
from utils.logger import create_logger
from app.config import settings

log = create_logger("api_status")

router = APIRouter()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        log(f"WebSocket connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        log(f"WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, data: Dict[str, Any]):
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)

manager = ConnectionManager()

# Staleness threshold in seconds (2 hours)
STALENESS_THRESHOLD_SECONDS = 7200

# Canonical sensor keys to expose
SENSOR_KEYS = [
    "interior_temp",
    "interior_humidity",
    "exterior_temp",
    "exterior_humidity",
    "satellite_battery",
    "satellite_pressure",
]


def check_staleness(last_seen: Dict[str, str], key: str) -> bool:
    """Check if a sensor reading is stale.
    
    Args:
        last_seen: Dict mapping sensor keys to ISO timestamps
        key: Sensor key to check
    
    Returns:
        True if the reading is older than STALENESS_THRESHOLD_SECONDS
    """
    timestamp_str = last_seen.get(key)
    if not timestamp_str:
        return True  # No timestamp = stale
    
    try:
        # Parse ISO timestamp
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        last_time = datetime.fromisoformat(timestamp_str)
        
        # Make timezone-aware if not already
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        
        age = datetime.now(timezone.utc) - last_time
        return age.total_seconds() > STALENESS_THRESHOLD_SECONDS
    except (ValueError, TypeError):
        return True  # Parse error = stale


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get current sensor status with staleness flags.
    
    Returns:
        {
            "sensors": { sensor values },
            "stale": { sensor staleness flags },
            "last_seen": { sensor timestamps },
            "updated_at": "ISO timestamp"
        }
    """
    status_path = settings.status_path if settings else "/app/data/status.json"
    
    # Load status.json
    raw_data = atomic_read_json(status_path, default={})
    
    sensors_raw = raw_data.get("sensors", {})
    last_seen = raw_data.get("last_seen", {})
    updated_at = raw_data.get("updated_at", datetime.now(timezone.utc).isoformat())
    
    # Extract and normalize sensor values
    sensors = {}
    stale = {}
    last_seen_out = {}
    
    for key in SENSOR_KEYS:
        # Get sensor value (handle both flat and nested formats)
        value = sensors_raw.get(key)
        
        # Round floats to 1 decimal place
        if isinstance(value, float):
            value = round(value, 1)
        
        sensors[key] = value
        stale[key] = check_staleness(last_seen, key)
        
        if key in last_seen:
            last_seen_out[key] = last_seen[key]
    
    log(f"Status request: {len(sensors)} sensors, {sum(stale.values())} stale")
    
    return {
        "sensors": sensors,
        "stale": stale,
        "last_seen": last_seen_out,
        "updated_at": updated_at,
    }


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket endpoint for real-time sensor updates.
    
    Sends sensor status every 10 seconds to connected clients.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Get current status
            status_path = settings.status_path if settings else "/app/data/status.json"
            raw_data = atomic_read_json(status_path, default={})
            
            sensors_raw = raw_data.get("sensors", {})
            last_seen = raw_data.get("last_seen", {})
            updated_at = raw_data.get("updated_at", datetime.now(timezone.utc).isoformat())
            
            sensors = {}
            stale = {}
            
            for key in SENSOR_KEYS:
                value = sensors_raw.get(key)
                if isinstance(value, float):
                    value = round(value, 1)
                sensors[key] = value
                stale[key] = check_staleness(last_seen, key)
            
            # Send update to this client
            await websocket.send_json({
                "type": "status",
                "sensors": sensors,
                "stale": stale,
                "updated_at": updated_at,
            })
            
            # Wait 10 seconds before next update
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        log(f"WebSocket error: {e}")
        manager.disconnect(websocket)
