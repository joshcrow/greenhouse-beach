"""Stream proxy router for HLS live stream from Greenhouse Pi.

This proxies the HLS stream from the Pi's mediamtx server through
the Cloudflare tunnel, avoiding direct exposure of the Pi.
"""

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import StreamingResponse

from utils.logger import create_logger

log = create_logger("api_stream")

router = APIRouter()

# Pi's mediamtx HLS endpoint (accessible via Tailscale)
GREENHOUSE_PI_IP = os.getenv("GREENHOUSE_PI_IP", "100.82.42.56")
HLS_BASE_URL = f"http://{GREENHOUSE_PI_IP}:8888"


@router.get("/stream/{path:path}")
async def proxy_hls_stream(path: str) -> Response:
    """Proxy HLS stream requests to the Greenhouse Pi.
    
    This allows the website to access the live stream without
    exposing the Pi directly to the internet.
    
    Args:
        path: The HLS file path (e.g., cam/index.m3u8, cam/segment.ts)
    
    Returns:
        Proxied response from mediamtx
    """
    target_url = f"{HLS_BASE_URL}/{path}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(target_url)
            
            if response.status_code != 200:
                log(f"HLS proxy error: {response.status_code} for {path}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Stream unavailable"
                )
            
            # Determine content type based on path
            if path.endswith('.m3u8'):
                content_type = 'application/vnd.apple.mpegurl'
            elif path.endswith('.ts'):
                content_type = 'video/mp2t'
            elif path.endswith('.mp4'):
                content_type = 'video/mp4'
            else:
                content_type = response.headers.get('content-type', 'application/octet-stream')
            
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Access-Control-Allow-Origin": "*",
                }
            )
    
    except httpx.TimeoutException:
        log(f"HLS proxy timeout for {path}")
        raise HTTPException(status_code=504, detail="Stream timeout")
    except httpx.RequestError as e:
        log(f"HLS proxy error: {e}")
        raise HTTPException(status_code=503, detail="Stream unavailable")
