"""FastAPI application for Greenhouse Gazette Web.

This module provides the REST API and WebSocket endpoints for the
STC web dashboard (straightouttacolington.com).

Usage:
    uvicorn web.api.main:app --host 0.0.0.0 --port 8000
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Add project paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from utils.logger import create_logger
from web.api.routers import status, narrative, riddle, charts, camera, stream

log = create_logger("web_api")

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    log("Starting Greenhouse Gazette Web API")
    yield
    log("Shutting down Greenhouse Gazette Web API")


app = FastAPI(
    title="Greenhouse Gazette API",
    description="REST API for the STC web dashboard",
    version="2.1.0",
    lifespan=lifespan,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
ALLOWED_ORIGINS = [
    "https://straightouttacolington.com",
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include routers
app.include_router(status.router, prefix="/api", tags=["Status"])
app.include_router(narrative.router, prefix="/api", tags=["Narrative"])
app.include_router(riddle.router, prefix="/api", tags=["Riddle"])
app.include_router(charts.router, prefix="/api", tags=["Charts"])
app.include_router(camera.router, prefix="/api", tags=["Camera"])
app.include_router(stream.router, prefix="/api", tags=["Stream"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "service": "greenhouse-gazette-web"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    log(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred. Please try again.",
        },
    )


# Mount timelapse static files
TIMELAPSE_DIR = PROJECT_ROOT / "data" / "www" / "timelapses"
if TIMELAPSE_DIR.exists():
    app.mount("/static/timelapses", StaticFiles(directory=str(TIMELAPSE_DIR)), name="timelapses")

# Mount static files (React build) - only if directory exists
# In Docker: /app/web/dist, in dev: web/frontend/dist
STATIC_DIR = PROJECT_ROOT / "web" / "dist"
if not STATIC_DIR.exists():
    STATIC_DIR = PROJECT_ROOT / "web" / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
